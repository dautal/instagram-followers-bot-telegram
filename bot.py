from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

# Load environment variables from .env so the bot token stays out of the code.
from dotenv import load_dotenv
# Core Telegram types used by the bot.
from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from instagram_compare import (
    InstagramExportError,
    compare_usernames,
    load_instagram_export,
)


# Basic logging makes it easier to see uploads and errors while the bot is running.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger(__name__)

load_dotenv()


async def _post_init(application: Application) -> None:
    # These commands show up in Telegram when the user types "/".
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Show instructions and export steps"),
            BotCommand("help", "Show instructions"),
            BotCommand("check", "Run the comparison again"),
            BotCommand("reset", "Clear uploaded files and start over"),
        ]
    )


def _get_storage_dir(context: ContextTypes.DEFAULT_TYPE) -> Path:
    # Each chat gets its own temporary folder so uploaded files stay separated.
    temp_dir = context.chat_data.get("temp_dir")
    if temp_dir is None:
        temp_dir = TemporaryDirectory(prefix="ig_compare_")
        context.chat_data["temp_dir"] = temp_dir
    return Path(temp_dir.name)


def _build_result_message(result: dict[str, list[str] | int]) -> str:
    # Pull the two one-sided lists out so the template below reads more clearly.
    followers_only = result["followers_only"]
    following_only = result["following_only"]

    # Turn each list into message-friendly text for Telegram.
    followers_only_text = (
        "\n".join(f"@{username}" for username in followers_only) if followers_only else "None"
    )
    following_only_text = (
        "\n".join(f"@{username}" for username in following_only) if following_only else "None"
    )

    # Telegram supports a small subset of HTML, so we use <b> for bold section headers.
    return (
        "<b>Instagram Comparison Complete</b>\n\n"
        "<b>Summary</b>\n"
        f"Followers: {result['followers_count']}\n"
        f"Following: {result['following_count']}\n"
        f"Mutual: {result['mutual_count']}\n"
        f"Follows you, but you do not follow back: {result['followers_only_count']}\n"
        f"You follow, but they do not follow you back: {result['following_only_count']}\n\n"
        "<b>People Who Follow You, But You Do Not Follow Back</b>\n"
        f"{followers_only_text}\n\n"
        "<b>People You Follow, But Who Do Not Follow You Back</b>\n"
        f"{following_only_text}\n\n"
        "If you want to do another check, send me the files again."
    )


async def _send_comparison(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Uploaded files are cached in chat_data after parsing.
    uploads = context.chat_data.get("uploads", {})
    if "followers" not in uploads or "following" not in uploads:
        await update.message.reply_text(
            "I need both files first. Please upload `followers_1.json` and `following.json` as documents."
        )
        return

    # We compare the already-parsed username sets instead of rereading the files every time.
    followers = uploads["followers"]["usernames"]
    following = uploads["following"]["usernames"]
    result = compare_usernames(followers, following)
    await update.message.reply_text(
        _build_result_message(result),
        parse_mode=ParseMode.HTML,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Create the uploads container for this chat if it does not exist yet.
    context.chat_data.setdefault("uploads", {})
    await update.message.reply_text(
        "Send me your Instagram `followers_1.json` and `following.json` files as documents.\n\n"
        "To export them from Instagram:\n"
        "1. Go to Accounts Center\n"
        "2. Open Your information and permissions\n"
        "3. Select Download your information\n"
        "4. Choose Download or transfer information\n"
        "5. Pick your Instagram account\n"
        "6. Select Some of your information\n"
        "7. Open Customize information and clear all\n"
        "8. In Connections, choose only Followers and following\n"
        "9. Set Date range to All time\n"
        "10. Set Format to JSON\n"
        "11. Export to device\n\n"
        "After I receive both files, I will compare them and show:\n"
        "- who follows you but you do not follow back\n"
        "- who you follow but who do not follow you back\n\n"
        "When you want to do another check, just send the files again.\n"
        "Use /check to rerun the current comparison or /reset to start over."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Delete this chat's temporary upload folder and forget the parsed data.
    temp_dir = context.chat_data.pop("temp_dir", None)
    if temp_dir is not None:
        temp_dir.cleanup()
    context.chat_data["uploads"] = {}
    await update.message.reply_text("Cleared the uploaded files for this chat. Send them again when ready.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Help just reuses the same instructions as /start.
    await start(update, context)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Re-run the comparison with the files already uploaded in this chat.
    await _send_comparison(update, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # This allows a natural-language trigger in addition to the /check command.
    message = update.message
    if message is None or not message.text:
        return

    if message.text.strip().lower() == "check followers vs following":
        await _send_comparison(update, context)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Telegram sends uploaded files as documents, so this is the main upload handler.
    message = update.message
    document = message.document

    if document is None:
        return

    # Only JSON exports are valid for this bot.
    if not document.file_name.lower().endswith(".json"):
        await message.reply_text("Please upload Instagram export files in `.json` format.")
        return

    # Save the uploaded file into this chat's temporary folder.
    storage_dir = _get_storage_dir(context)
    file_path = storage_dir / document.file_name
    telegram_file = await document.get_file()
    await telegram_file.download_to_drive(custom_path=str(file_path))

    try:
        # Figure out which export type this is and extract usernames from it.
        export_type, usernames = load_instagram_export(file_path)
    except (InstagramExportError, ValueError) as exc:
        LOGGER.warning("Failed to parse upload %s: %s", document.file_name, exc)
        file_path.unlink(missing_ok=True)
        await message.reply_text(
            "I could not read that file as an Instagram followers/following export.\n"
            f"Reason: {exc}"
        )
        return

    # Store the parsed result in memory so /check can reuse it instantly.
    uploads = context.chat_data.setdefault("uploads", {})
    uploads[export_type] = {
        "file_name": document.file_name,
        "path": str(file_path),
        # Sets are perfect here because duplicates do not matter for username matching.
        "usernames": usernames,
    }

    await message.reply_text(
        f"Saved `{document.file_name}` as your `{export_type}` export with {len(usernames)} usernames."
    )

    # Try the comparison right away after each upload.
    await _send_comparison(update, context)


def build_application(token: str) -> Application:
    # Build the Telegram app, then attach command and message handlers.
    application = Application.builder().token(token).post_init(_post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return application


def main() -> None:
    # The bot token comes from .env or the shell environment.
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable first.")

    # Polling means the bot keeps asking Telegram for new messages in a loop.
    application = build_application(token)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
