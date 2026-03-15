from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
from telegram import Update
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


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger(__name__)

load_dotenv()


def _get_storage_dir(context: ContextTypes.DEFAULT_TYPE) -> Path:
    # Keep uploads in a per-chat temporary folder for the current bot session.
    temp_dir = context.chat_data.get("temp_dir")
    if temp_dir is None:
        temp_dir = TemporaryDirectory(prefix="ig_compare_")
        context.chat_data["temp_dir"] = temp_dir
    return Path(temp_dir.name)


def _build_result_message(result: dict[str, list[str] | int]) -> str:
    followers_only = result["followers_only"]
    following_only = result["following_only"]

    followers_only_text = (
        "\n".join(f"@{username}" for username in followers_only) if followers_only else "None"
    )
    following_only_text = (
        "\n".join(f"@{username}" for username in following_only) if following_only else "None"
    )

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
    uploads = context.chat_data.get("uploads", {})
    if "followers" not in uploads or "following" not in uploads:
        await update.message.reply_text(
            "I need both files first. Please upload `followers_1.json` and `following.json` as documents."
        )
        return

    # Usernames are parsed once on upload and cached in chat_data for reuse.
    followers = uploads["followers"]["usernames"]
    following = uploads["following"]["usernames"]
    result = compare_usernames(followers, following)
    await update.message.reply_text(
        _build_result_message(result),
        parse_mode=ParseMode.HTML,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data.setdefault("uploads", {})
    await update.message.reply_text(
        "Send me your Instagram `followers_1.json` and `following.json` files as documents.\n\n"
        "After I receive both, I will compare them and show:\n"
        "- who follows you but you do not follow back\n"
        "- who you follow but who do not follow you back\n\n"
        "When you want to run another check, just send the files again.\n"
        "Use /reset if you want to start over."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    temp_dir = context.chat_data.pop("temp_dir", None)
    if temp_dir is not None:
        temp_dir.cleanup()
    context.chat_data["uploads"] = {}
    await update.message.reply_text("Cleared the uploaded files for this chat. Send them again when ready.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_comparison(update, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or not message.text:
        return

    if message.text.strip().lower() == "check followers vs following":
        await _send_comparison(update, context)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    document = message.document

    if document is None:
        return

    if not document.file_name.lower().endswith(".json"):
        await message.reply_text("Please upload Instagram export files in `.json` format.")
        return

    storage_dir = _get_storage_dir(context)
    file_path = storage_dir / document.file_name
    telegram_file = await document.get_file()
    await telegram_file.download_to_drive(custom_path=str(file_path))

    try:
        # Detect whether the upload is the followers or following export.
        export_type, usernames = load_instagram_export(file_path)
    except (InstagramExportError, ValueError) as exc:
        LOGGER.warning("Failed to parse upload %s: %s", document.file_name, exc)
        file_path.unlink(missing_ok=True)
        await message.reply_text(
            "I could not read that file as an Instagram followers/following export.\n"
            f"Reason: {exc}"
        )
        return

    uploads = context.chat_data.setdefault("uploads", {})
    uploads[export_type] = {
        "file_name": document.file_name,
        "path": str(file_path),
        # Sets make the comparison fast and automatically deduplicate usernames.
        "usernames": usernames,
    }

    await message.reply_text(
        f"Saved `{document.file_name}` as your `{export_type}` export with {len(usernames)} usernames."
    )

    await _send_comparison(update, context)


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return application


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable first.")

    application = build_application(token)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
