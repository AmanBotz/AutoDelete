import os
import asyncio
import time
from threading import Thread
from queue import Queue
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask

# Configuration
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# MongoDB Setup
mongo = MongoClient(MONGO_URI)
db = mongo.auto_delete_bot
settings = db.settings
message_queue = Queue()

# Pyrogram Client
bot = Client("auto_delete_bot", API_ID, API_HASH, bot_token=BOT_TOKEN)

# Flask Server
flask_app = Flask(__name__)
@flask_app.route('/')
def health_check():
    return "Bot Operational", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=8000)

async def deletion_worker():
    while True:
        try:
            chat_id, message_id = message_queue.get()
            delay = settings.find_one({"chat_id": chat_id})["delay"]
            
            await asyncio.sleep(delay)
            await bot.delete_messages(chat_id, message_id)
            
            message_queue.task_done()
        except Exception as e:
            print(f"Deletion Error: {e}")

@bot.on_message(filters.group & ~filters.service)
async def track_message(_, message: Message):
    try:
        config = settings.find_one({"chat_id": message.chat.id})
        if not config or "delay" not in config:
            return
        
        message_queue.put((message.chat.id, message.id))
    except Exception as e:
        print(f"Tracking Error: {e}")

@bot.on_message(filters.command("setdelay") & filters.group)
async def set_delay(_, message: Message):
    user = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in ("creator", "administrator"):
        await message.reply("Admin rights required!")
        return
    
    try:
        delay = max(10, int(message.command[1]))
        settings.update_one(
            {"chat_id": message.chat.id},
            {"$set": {"delay": delay}},
            upsert=True
        )
        await message.reply(f"⏳ Messages will auto-delete after {delay}s")
    except (IndexError, ValueError):
        await message.reply("Usage: /setdelay <seconds>")

@bot.on_start
async def initialize(client):
    asyncio.create_task(deletion_worker())

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run()
