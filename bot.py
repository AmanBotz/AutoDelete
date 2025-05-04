import os
import asyncio
import time
from threading import Thread
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask

# Load environment variables
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['auto_delete_bot']
groups = db['groups']
messages = db['messages']

# Pyrogram client
app = Client("auto_delete_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Flask server setup
flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return "Auto Delete Bot is Running!", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=8000)

# Scheduler for message deletion
async def message_scheduler():
    while True:
        current_time = time.time()
        try:
            # Get messages due for deletion
            due_messages = list(messages.find({"deletion_time": {"$lte": current_time}}))
            
            # Group messages by chat ID
            messages_by_chat = {}
            for msg in due_messages:
                chat_id = msg['chat_id']
                if chat_id not in messages_by_chat:
                    messages_by_chat[chat_id] = []
                messages_by_chat[chat_id].append(msg['message_id'])
            
            # Delete messages in bulk per chat
            for chat_id, msg_ids in messages_by_chat.items():
                try:
                    # Split into chunks of 100 (Telegram API limit)
                    for i in range(0, len(msg_ids), 100):
                        chunk = msg_ids[i:i+100]
                        await app.delete_messages(chat_id, chunk)
                    
                    # Remove deleted messages from DB
                    messages.delete_many({
                        "chat_id": chat_id,
                        "message_id": {"$in": msg_ids}
                    })
                except Exception as e:
                    print(f"Error deleting messages in {chat_id}: {e}")
            
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Scheduler error: {e}")
            await asyncio.sleep(10)

# Telegram command handlers
@app.on_message(filters.command("start"))
async def start_cmd(_, message: Message):
    await message.reply("🕒 Auto Delete Bot\n\nAdmins can set delete delay with /setdelay <seconds>")

@app.on_message(filters.command("setdelay") & filters.group)
async def setdelay_cmd(_, message: Message):
    # Check if user is admin
    user = await app.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in ("creator", "administrator"):
        await message.reply("❌ Only admins can use this command!")
        return
    
    # Validate input
    try:
        delay = int(message.command[1])
        if delay < 10:
            await message.reply("⚠️ Minimum delay is 10 seconds")
            return
    except (IndexError, ValueError):
        await message.reply("ℹ️ Usage: /setdelay <seconds>")
        return
    
    # Update database
    groups.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"delay": delay}},
        upsert=True
    )
    await message.reply(f"✅ Messages will now be automatically deleted after {delay} seconds")

# Message handler
@app.on_message(filters.group & ~filters.service)
async def track_message(_, message: Message):
    try:
        # Get group settings
        group = groups.find_one({"chat_id": message.chat.id})
        if not group or 'delay' not in group:
            return
        
        # Calculate deletion time
        deletion_time = time.time() + group['delay']
        
        # Store message in database
        messages.insert_one({
            "chat_id": message.chat.id,
            "message_id": message.id,
            "deletion_time": deletion_time
        })
    except Exception as e:
        print(f"Error tracking message: {e}")

# Start scheduler when bot starts
@app.on_start()
async def startup():
    asyncio.create_task(message_scheduler())

if __name__ == "__main__":
    # Start Flask server in separate thread
    Thread(target=run_flask, daemon=True).start()
    # Start Pyrogram client
    app.run()
