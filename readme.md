# Telegram Auto Deleter Bot

A Telegram bot built with [Pyrogram](https://docs.pyrogram.org/) that automatically deletes messages from group chats after a delay. The delay can be set by group admins using a command. Also includes a lightweight Flask server on port 8000.

## Features

- Deletes messages after a delay (default: 5 seconds)
- Admins can configure delay using `/setdelay <seconds>`
- Persistent storage via MongoDB
- Flask health check endpoint, PORT 8000
- Ping Url every 30 seconds for keeping bot live

---

## Setup

### Environment Variables

```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
MONGO_URI=your_mongodb_uri
PING_URL=your_bot_service_url
```

### Run Command 
`python3 bot.py`
