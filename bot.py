import os
import asyncio
import re
from threading import Thread
from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatMemberUpdated,
    Message
)
from flask import Flask, request, jsonify
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
import aiohttp
from functools import wraps

# Configuration
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH"))
BOT_TOKEN = os.getenv("BOT_TOKEN"))
MONGO_URI = os.getenv("MONGO_URI"))
PING_URL = os.getenv("PING_URL"))
PING_INTERVAL = int(os.getenv("PING_INTERVAL", 30)))
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret")

# Database setup
mongo = MongoClient(MONGO_URI)
db = mongo['auto_delete_pro']
settings_col = db['settings']
chats_col = db['chats']
user_ctx_col = db['user_context']

# Create indexes
settings_col.create_index([("_id", ASCENDING)])
chats_col.create_index([("_id", ASCENDING)])

app = Client("auto_delete_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
server = Flask(__name__)
server.secret_key = SECRET_KEY

# Helpers
def parse_delay(text: str) -> int:
    if not re.match(r"^\d+[smhd]$", text):
        raise ValueError("Invalid format. Use <number><s|m|h|d>")
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return int(text[:-1]) * units[text[-1]]

async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except Exception:
        return False

def protected(endpoint):
    @wraps(endpoint)
    def wrapper(*args, **kwargs):
        if request.headers.get('X-API-KEY') != SECRET_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return endpoint(*args, **kwargs)
    return wrapper

# Database operations
async def get_chat_settings(chat_id: int):
    try:
        doc = settings_col.find_one({"_id": str(chat_id)})
        return doc or {"user": 0, "bot": 0, "exclude": []}
    except PyMongoError:
        return {"user": 0, "bot": 0, "exclude": []}

async def update_chat_settings(chat_id: int, update: dict):
    try:
        settings_col.update_one(
            {"_id": str(chat_id)},
            {"$set": update},
            upsert=True
        )
    except PyMongoError as e:
        print(f"MongoDB error: {e}")

# Handlers
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    buttons = [
        [InlineKeyboardButton("📋 List Managed Chats", callback_data="list_chats")],
        [InlineKeyboardButton("⚙ Bot Documentation", url="https://example.com/docs")]
    ]
    await message.reply(
        "🤖 **AutoDelete Pro**\n\n"
        "Configure automatic message deletion for your groups/channels.\n"
        "- Set different delays for users and bots\n"
        "- Exclude specific users from deletion\n"
        "- Cloud-controlled settings\n\n"
        "Use buttons below to manage your chats:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"^list_chats$"))
async def list_chats_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        chats = list(chats_col.find({"admins": user_id}))
        buttons = []
        for chat in chats:
            btn = InlineKeyboardButton(
                chat.get('title', chat['_id']),
                callback_data=f"manage_{chat['_id']}"
            )
            buttons.append([btn])
        
        await callback.edit_message_text(
            "Select a chat to manage:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        await callback.answer("Error fetching chats", show_alert=True)

@app.on_callback_query(filters.regex(r"^manage_(\-?\d+)$"))
async def manage_chat_handler(client: Client, callback: CallbackQuery):
    chat_id = int(callback.matches[0].group(1))
    user_id = callback.from_user.id
    
    if not await is_admin(chat_id, user_id):
        return await callback.answer("You must be an admin in this chat", show_alert=True)
    
    settings = await get_chat_settings(chat_id)
    buttons = [
        [InlineKeyboardButton(f"User Delay: {settings['user']}s", callback_data=f"set_user_{chat_id}")],
        [InlineKeyboardButton(f"Bot Delay: {settings['bot']}s", callback_data=f"set_bot_{chat_id}")],
        [InlineKeyboardButton("Exclude Users", callback_data=f"exclude_{chat_id}")]
    ]
    await callback.edit_message_text(
        f"⚙ Managing Chat ID: {chat_id}\n"
        "Configure deletion settings:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_message(filters.group | filters.channel & ~filters.service)
async def message_handler(client: Client, message: Message):
    chat_id = message.chat.id
    settings = await get_chat_settings(chat_id)
    
    if message.from_user and message.from_user.id in settings.get("exclude", []):
        return
    
    delay = settings["bot"] if (message.from_user and message.from_user.is_bot) else settings["user"]
    
    if delay > 0:
        asyncio.create_task(delete_message(message, delay))

async def delete_message(message: Message, delay: int):
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        print(f"Error deleting message: {e}")

# Flask endpoints
@server.route('/ping', methods=['POST'])
@protected
def ping():
    return jsonify({"status": "OK", "interval": PING_INTERVAL})

@server.route('/broadcast', methods=['POST'])
@protected
def broadcast():
    data = request.json
    message = data.get("message")
    
    async def _broadcast():
        for chat in chats_col.find():
            try:
                await app.send_message(chat['_id'], message)
            except Exception:
                continue
    asyncio.run_coroutine_threadsafe(_broadcast(), app.loop)
    return jsonify({"status": "Broadcast started"})

# System tasks
async def ping_task():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(PING_URL)
        except Exception:
            pass
        await asyncio.sleep(PING_INTERVAL)

def run_flask():
    server.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)), use_reloader=False)

async def main():
    await app.start()
    asyncio.create_task(ping_task())
    Thread(target=run_flask, daemon=True).start()
    await idle()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(app.stop())
        mongo.close()
