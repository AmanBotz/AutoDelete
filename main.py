import asyncio
from pyrogram import Client
from flask import Flask
from threading import Thread

from config import API_ID, API_HASH, BOT_TOKEN
from deleter import process_queue
from pinger import keep_alive
import handlers  # noqa: F401

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive."

def run_flask():
    app.run(host="0.0.0.0", port=8000)

bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def main():
    Thread(target=run_flask).start()
    await bot.start()
    asyncio.create_task(keep_alive())
    await process_queue()

if __name__ == "__main__":
    asyncio.run(main())
