import asyncio
import os
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, enums
from pyrogram.types import Message

# Load environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
SESSION_NAME = os.getenv("SESSION_NAME", "autodeleter_bot")

# MongoDB setup
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["autodeleter"]
settings_collection = db["settings"]

# Pyrogram client
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Flask server
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Auto Deleter Bot is running."

# Schedule deletion
async def schedule_deletion(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id, message_id)
    except Exception as e:
        print(f"[ERROR] Failed to delete message {message_id} in chat {chat_id}: {e}")

# Check admin status using enums.ChatMembersFilter.ADMINISTRATORS
async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        async for member in app.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
            if member.user.id == user_id:
                return True
        return False
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False

# Set delay command
@app.on_message(filters.command("setdelay") & filters.group)
async def set_delay(client: Client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_admin(chat_id, user_id):
        await message.reply("Only admins can set the deletion delay.")
        return

    try:
        delay = int(message.text.split()[1])
        if delay < 0:
            raise ValueError
    except (IndexError, ValueError):
        await message.reply("Usage: /setdelay <seconds> (non-negative integer)")
        return

    await settings_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"delay": delay}},
        upsert=True
    )

    await message.reply(f"Message deletion delay set to {delay} seconds.")

# Handle all messages in groups (excluding service messages)
@app.on_message(filters.group & ~filters.service)
async def handle_message(client: Client, message: Message):
    chat_id = message.chat.id
    msg_id = message.id

    setting = await settings_collection.find_one({"chat_id": chat_id})
    delay = setting["delay"] if setting and "delay" in setting else 5  # default to 5 seconds

    asyncio.create_task(schedule_deletion(chat_id, msg_id, delay))

if __name__ == "__main__":
    import threading

    def run_flask():
        flask_app.run(host="0.0.0.0", port=8000)

    threading.Thread(target=run_flask).start()
    app.run()
