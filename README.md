# Instagram Followers Telegram Bot

A simple Python Telegram bot that compares Instagram export files and shows:

- people who follow you, but you do not follow back
- people you follow, but who do not follow you back

It works with Instagram's exported `followers_1.json` and `following.json` files.

## Features

- Accepts Instagram export files directly in Telegram
- Detects whether each upload is `followers` or `following`
- Compares usernames using case-insensitive matching
- Sends the result back as a formatted Telegram message
- Lets you rerun the comparison with `/check` without restarting the bot

## Project Structure

- `bot.py`: Telegram bot logic, file downloads, commands, message formatting
- `instagram_compare.py`: Instagram JSON parsing and username comparison logic
- `requirements.txt`: Python dependencies
- `.env.example`: example environment file for the bot token

## How It Works

Instagram uses two different JSON shapes:

- `followers_1.json`: usernames are inside `string_list_data[].value`
- `following.json`: usernames are usually inside each item's `title`

The bot parses both formats, normalizes usernames, and compares them with Python sets.

## Setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather).
2. Clone this repository or open the project folder.
3. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Create your environment file:

```bash
cp .env.example .env
```

6. Open `.env` and add your real Telegram token:

```env
TELEGRAM_BOT_TOKEN=your_real_bot_token_here
```

7. Start the bot:

```bash
python3 bot.py
```

## Usage

1. Open your bot in Telegram
2. Send `/start`
3. Upload `followers_1.json`
4. Upload `following.json`
5. Read the formatted result message

If you want to run the comparison again without reuploading immediately, send:

```text
/check
```

or:

```text
check followers vs following
```

## Commands

- `/start`: show instructions
- `/help`: show instructions
- `/check`: run the comparison again using the current uploaded files
- `/reset`: clear uploaded files for the current chat

## Notes

- Username matching is case-insensitive
- Duplicate usernames do not affect results
- Uploaded files are stored in a temporary folder while the bot is running
- The bot does not keep uploads permanently after a full restart
- `.env` should never be committed to GitHub
