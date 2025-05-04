import os
import asyncio
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from mongoengine import connect, Document, StringField, IntField

app = Flask(__name__)
app.debug = False

# MongoDB configuration
connect(db="auto_delete_bot", host=os.environ.get("MONGO_URI"))

# Model for group settings
class GroupSettings(Document):
    chat_id = StringField(required=True, unique=True)
    delete_after_seconds = IntField(default=60)

# Pyrogram client setup
api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

bot = Client("auto_delete_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

@bot.on_message(filters.command(["setdelay"]) & filters.group)
async def set_delay(client: Client, message: Message):
    user = message.from_user
    if not user or not await is_admin(message.chat.id, user.id):
        await message.reply("Only admins can set deletion delay!")
        return

    try:
        delay = int(message.command[1])
        if delay < 10:
            raise ValueError("Delay must be at least 10 seconds")
    except (IndexError, ValueError):
        await message.reply("Invalid format. Use /setdelay <seconds> (min 10)")
        return

    GroupSettings.objects(chat_id=str(message.chat.id)).update_one(
        upsert=True,
        set__delete_after_seconds=delay
    )
    await message.reply(f"Auto-delete delay set to {delay} seconds!")

@bot.on_message(filters.group & ~filters.service)
async def track_message(client: Client, message: Message):
    try:
        settings = GroupSettings.objects.get(chat_id=str(message.chat.id))
        delay = settings.delete_after_seconds
    except GroupSettings.DoesNotExist:
        delay = 60  # Default delay

    # Schedule message deletion
    await schedule_deletion(message, delay)

async def schedule_deletion(message: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.delete()
    except Exception as e:
        print(f"Error deleting message: {e}")

def run_flask():
    app.run(host='0.0.0.0', port=8000)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    print("Flask server started on port 8000")
    
    bot.run()
    print("Bot started")
