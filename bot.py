import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pymongo import MongoClient
from flask import Flask
import threading
import time
import os
from datetime import datetime, timedelta

api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")
mongo = MongoClient(os.environ.get("MONGO_URI"))
db = mongo['autodelete']
PING_URL = os.environ.get("PING_URL")

app = Flask(__name__)
queue = asyncio.Queue()
bot = Client("autodelete-bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

time_units = ["seconds", "minutes", "days", "weeks", "months", "years"]
unit_seconds = {
    "seconds": 1,
    "minutes": 60,
    "days": 86400,
    "weeks": 604800,
    "months": 2592000,
    "years": 31536000
}

def get_settings(chat_id):
    data = db.settings.find_one({"chat_id": chat_id}) or {}
    return {
        "bot_delay": data.get("bot_delay", 120),
        "user_delay": data.get("user_delay", 3),
        "unit": data.get("unit", "seconds")
    }

def save_settings(chat_id, key, value):
    db.settings.update_one({"chat_id": chat_id}, {"$set": {key: value}}, upsert=True)

@bot.on_message(filters.command("start"))
async def start(_, msg):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")],
        [InlineKeyboardButton("➕ Add to Channel", url="https://t.me/"), InlineKeyboardButton("List Chats", callback_data="list_chats")],
        [InlineKeyboardButton("Set Delays", callback_data="set_delay")]
    ])
    await msg.reply("Welcome to AutoDelete Bot.", reply_markup=keyboard)

@bot.on_message(filters.group | filters.channel)
async def handle_msg(_, msg: Message):
    if msg.sender_chat:
        sender = msg.sender_chat.id
    elif msg.from_user:
        sender = msg.from_user.id
    else:
        return
    settings = get_settings(msg.chat.id)
    is_bot = msg.from_user and msg.from_user.is_bot
    delay = settings["bot_delay"] if is_bot else settings["user_delay"]
    await queue.put((msg.chat.id, msg.id, delay))

@bot.on_chat_member_updated()
async def on_added(_, update):
    if update.new_chat_member.user.id == (await bot.get_me()).id:
        perms = update.chat_member.chat.permissions
        if not (perms and perms.delete_messages):
            await bot.send_message(update.chat.id, "I need delete message permission to work.")

@bot.on_callback_query()
async def callback(bot, query):
    data = query.data
    chat_id = query.message.chat.id
    if data == "list_chats":
        user_id = query.from_user.id
        chats = db.settings.find()
        result = []
        for c in chats:
            try:
                member = await bot.get_chat_member(c["chat_id"], user_id)
                if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                    result.append(str(c["chat_id"]))
            except:
                continue
        txt = "Chats:\n" + "\n".join(result) if result else "No chats found."
        await query.message.edit_text(txt)
    elif data == "set_delay":
        settings = get_settings(chat_id)
        unit = settings.get("unit", "seconds")
        keyboard = [[InlineKeyboardButton(u, callback_data=f"unit_{u}")] for u in time_units]
        keyboard.append([
            InlineKeyboardButton("-1", callback_data="dec"),
            InlineKeyboardButton("+1", callback_data="inc")
        ])
        keyboard.append([
            InlineKeyboardButton("For Bot Msg", callback_data="toggle_bot"),
            InlineKeyboardButton("For User Msg", callback_data="toggle_user")
        ])
        await query.message.edit_text(
            f"Current unit: {unit}\nUser Delay: {settings['user_delay']}\nBot Delay: {settings['bot_delay']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data.startswith("unit_"):
        unit = data.split("_", 1)[1]
        save_settings(chat_id, "unit", unit)
        await callback(bot, query)
    elif data in ["inc", "dec"]:
        settings = get_settings(chat_id)
        key = "bot_delay" if db.settings.find_one({"chat_id": chat_id}).get("mode", "user") == "bot" else "user_delay"
        value = settings[key]
        unit = settings["unit"]
        delta = 1 * unit_seconds[unit]
        new_val = max(1, value + delta if data == "inc" else value - delta)
        save_settings(chat_id, key, new_val)
        await callback(bot, query)
    elif data == "toggle_bot":
        db.settings.update_one({"chat_id": chat_id}, {"$set": {"mode": "bot"}})
        await callback(bot, query)
    elif data == "toggle_user":
        db.settings.update_one({"chat_id": chat_id}, {"$set": {"mode": "user"}})
        await callback(bot, query)

async def delete_worker():
    while True:
        chat_id, msg_id, delay = await queue.get()
        await asyncio.sleep(delay)
        try:
            await bot.delete_messages(chat_id, msg_id)
        except:
            pass

def run_flask():
    @app.route("/")
    def home():
        return "OK"
    def ping_loop():
        while True:
            try:
                import requests
                requests.get(PING_URL)
            except:
                pass
            time.sleep(30)
    threading.Thread(target=ping_loop).start()
    app.run(host="0.0.0.0", port=8000)

async def main():
    asyncio.create_task(delete_worker())
    await bot.start()
    run_flask()

if __name__ == "__main__":
    asyncio.run(main())
