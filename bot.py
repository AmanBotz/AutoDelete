import asyncio
import os
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import Message

# Load environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
SESSION_NAME = os.getenv("SESSION_NAME", "autodeleter_bot")

# Initialize MongoDB client
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["autodeleter"]
settings_collection = db["settings"]

# Initialize Pyrogram client
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize Flask app
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Auto Deleter Bot is running."

# Schedule deletion of a single message
async def schedule_deletion(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id, message_id)
    except Exception as e:
        print(f"[ERROR] Failed to delete message {message_id} in chat {chat_id}: {e}")

# Command to set delay
@app.on_message(filters.command("setdelay") & filters.group)
async def set_delay(client: Client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    try:
        admins = await client.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        if user_id not in admin_ids:
            await message.reply("Only admins can set the deletion delay.")
            return
    except Exception as e:
        await message.reply(f"Could not verify admin status: {e}")
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

# Handle all group messages
@app.on_message(filters.group & ~filters.service)
async def handle_message(client: Client, message: Message):
    chat_id = message.chat.id
    msg_id = message.id

    setting = await settings_collection.find_one({"chat_id": chat_id})
    delay = setting["delay"] if setting and "delay" in setting else 5  # Default delay of 5 seconds

    asyncio.create_task(schedule_deletion(chat_id, msg_id, delay))

if __name__ == "__main__":
    import threading

    def run_flask():
        flask_app.run(host="0.0.0.0", port=8000)

    threading.Thread(target=run_flask).start()
    app.run()
