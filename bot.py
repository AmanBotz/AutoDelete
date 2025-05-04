import os
import time
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pymongo import MongoClient
from datetime import datetime, timedelta

API_ID = int(os.getenv("API_ID", "YOUR_API_ID"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "YOUR_MONGODB_URI")
PING_URL = os.getenv("PING_URL", "https://yoururl.com")

app = Client("autodelete_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URI)
db = mongo.autodelete
chats_col = db.chats
users_col = db.users

flask_app = Flask(__name__)
selected_chats = {}

@flask_app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

def pinger():
    while True:
        try:
            import requests
            requests.get(PING_URL)
        except:
            pass
        time.sleep(30)

@app.on_message(filters.private & filters.command("start"))
async def start(client, message: Message):
    users_col.update_one({"_id": message.from_user.id}, {"$set": {"last_seen": datetime.utcnow()}}, upsert=True)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to Group", url=f"https://t.me/{client.me.username}?startgroup=start")],
        [InlineKeyboardButton("➕ Add me to Channel", url=f"https://t.me/{client.me.username}?startchannel=start")],
        [InlineKeyboardButton("📂 List My Chats", callback_data="list_chats")]
    ])
    await message.reply("Welcome! I can auto-delete messages from any group or channel after a delay. First, add me and give **Delete Messages** permission.", reply_markup=kb)

@app.on_callback_query(filters.regex("list_chats"))
async def list_chats(client, cb):
    user_id = cb.from_user.id
    chats = chats_col.find({"admins": user_id})
    buttons = []
    for chat in chats:
        title = chat.get("title", str(chat["_id"]))
        buttons.append([InlineKeyboardButton(title, callback_data=f"chat_{chat['_id']}")])
    if not buttons:
        await cb.answer("No chats found where you're an admin.")
        return
    await cb.message.edit("Select a chat to configure:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"chat_"))
async def select_chat(client, cb):
    chat_id = int(cb.data.split("_", 1)[1])
    selected_chats[cb.from_user.id] = chat_id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Set User Msg Delay", callback_data="set_user")],
        [InlineKeyboardButton("Set Bot Msg Delay", callback_data="set_bot")],
        [InlineKeyboardButton("Reset Settings", callback_data="reset")],
        [InlineKeyboardButton("Back", callback_data="list_chats")]
    ])
    await cb.message.edit(f"✅ Selected chat: `{chat_id}`\nNow choose what you want to configure:", reply_markup=kb)

@app.on_callback_query(filters.regex("reset"))
async def reset_settings(client, cb):
    user_id = cb.from_user.id
    chat_id = selected_chats.get(user_id)
    if not chat_id:
        await cb.answer("No chat selected.")
        return
    chats_col.update_one({"_id": chat_id}, {"$unset": {"user_delay": "", "bot_delay": ""}})
    await cb.answer("Reset done.")
    await cb.message.edit("Settings have been reset.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="list_chats")]]))

@app.on_callback_query(filters.regex("set_(user|bot)"))
async def set_delay_menu(client, cb):
    typ = cb.data.split("_")[1]
    buttons = [
        [InlineKeyboardButton("10s", callback_data=f"delay_{typ}_10s"), InlineKeyboardButton("1m", callback_data=f"delay_{typ}_1m")],
        [InlineKeyboardButton("5m", callback_data=f"delay_{typ}_5m"), InlineKeyboardButton("1h", callback_data=f"delay_{typ}_1h")],
        [InlineKeyboardButton("1d", callback_data=f"delay_{typ}_1d"), InlineKeyboardButton("1w", callback_data=f"delay_{typ}_1w")],
        [InlineKeyboardButton("1M", callback_data=f"delay_{typ}_1M"), InlineKeyboardButton("1y", callback_data=f"delay_{typ}_1y")],
        [InlineKeyboardButton("Back", callback_data="list_chats")]
    ]
    await cb.message.edit("Choose delay time:", reply_markup=InlineKeyboardMarkup(buttons))

def parse_duration(duration: str) -> int:
    unit = duration[-1]
    val = int(duration[:-1])
    mapping = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "M": 2592000, "y": 31536000}
    return val * mapping.get(unit, 0)

@app.on_callback_query(filters.regex(r"delay_(user|bot)_"))
async def set_delay(client, cb):
    typ, dur = cb.data.split("_")[1:]
    user_id = cb.from_user.id
    chat_id = selected_chats.get(user_id)
    if not chat_id:
        await cb.answer("No chat selected.")
        return
    seconds = parse_duration(dur)
    field = "user_delay" if typ == "user" else "bot_delay"
    chats_col.update_one({"_id": chat_id}, {"$set": {field: seconds}}, upsert=True)
    await cb.message.edit(f"✅ {typ.capitalize()} message delay set to {dur} for chat `{chat_id}`.")

@app.on_chat_member_updated()
async def on_added(client, update):
    if update.new_chat_member and update.new_chat_member.user.id == client.me.id:
        chat = await client.get_chat(update.chat.id)
        title = chat.title or "Unknown"
        admins = [m.user.id async for m in client.get_chat_members(chat.id, filter="administrators") if m.status == "administrator"]
        chats_col.update_one({"_id": chat.id}, {"$set": {"title": title, "admins": admins}}, upsert=True)
        try:
            await client.send_message(chat.id, "Thanks for adding me! Please give me 'Delete messages' permission.")
        except:
            pass
        for uid in admins:
            try:
                await client.send_message(uid, f"I'm added to `{title}` (`{chat.id}`)\nSelect it via 'List My Chats' to configure auto-delete.")
            except:
                pass

@app.on_message(filters.group | filters.channel)
async def auto_delete_handler(client, message: Message):
    if not message.chat or message.from_user is None:
        return
    data = chats_col.find_one({"_id": message.chat.id}) or {}
    delay = 0
    if message.from_user.id == client.me.id:
        delay = data.get("bot_delay", 0)
    else:
        delay = data.get("user_delay", 0)
    if delay > 0:
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=pinger).start()
    app.run()
