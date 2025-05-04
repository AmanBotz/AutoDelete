import os
import asyncio
from threading import Thread
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, jsonify
from pymongo import MongoClient
import aiohttp

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
PING_URL = os.getenv("PING_URL")
PING_INTERVAL = int(os.getenv("PING_INTERVAL", 30))

mongo = MongoClient(MONGO_URI)
db = mongo['auto_delete_bot']
settings_col = db['settings']

app = Client("auto_delete_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
server = Flask(__name__)

def get_settings(chat_id: str):
    doc = settings_col.find_one({"_id": chat_id})
    return {"user": doc.get("user", 0), "bot": doc.get("bot", 0)} if doc else {"user": 0, "bot": 0}

def set_settings(chat_id: str, user_delay=None, bot_delay=None):
    update = {}
    if user_delay is not None:
        update['user'] = user_delay
    if bot_delay is not None:
        update['bot'] = bot_delay
    settings_col.update_one({"_id": chat_id}, {"$set": update}, upsert=True)

def parse_delay(text: str) -> int:
    num = int(text[:-1])
    unit = text[-1]
    if unit == 's': return num
    if unit == 'm': return num * 60
    if unit == 'h': return num * 3600
    if unit == 'd': return num * 86400
    raise ValueError

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    bot = await c.get_me()
    buttons = [[InlineKeyboardButton("➕ Add to a Group", url=f"https://t.me/{bot.username}?startgroup=true")],
               [InlineKeyboardButton("➕ Add to a Channel", url=f"https://t.me/{bot.username}?startchannel=true")]]
    text = (
        "👋 Hello! I automatically delete messages in your chats after a set time.\n"
        "• Use /setdelay_user to configure how long before USER messages are removed.\n"
        "• Use /setdelay_bot to configure how long before BOT messages are removed.\n"
        "• In groups and channels, I’ll erase messages from all users and bots when time’s up!"
    )
    await m.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_message(filters.command("setdelay_user") & (filters.private | filters.group | filters.channel))
async def set_user_delay(c, m):
    chat_id = str(m.chat.id)
    try:
        delay = parse_delay(m.command[1])
    except:
        await m.reply("🚫 Invalid format. Use: /setdelay_user <number><s|m|h|d>, e.g., /setdelay_user 10m")
        return
    set_settings(chat_id, user_delay=delay)
    await m.reply(f"✅ User messages will be deleted {m.command[1]} after posting.")

@app.on_message(filters.command("setdelay_bot") & (filters.private | filters.group | filters.channel))
async def set_bot_delay(c, m):
    chat_id = str(m.chat.id)
    try:
        delay = parse_delay(m.command[1])
    except:
        await m.reply("🚫 Invalid format. Use: /setdelay_bot <number><s|m|h|d>, e.g., /setdelay_bot 30s")
        return
    set_settings(chat_id, bot_delay=delay)
    await m.reply(f"✅ Bot messages will be deleted {m.command[1]} after posting.")

async def schedule_deletion(c, m, delay):
    await asyncio.sleep(delay)
    try:
        await c.delete_messages(chat_id=m.chat.id, message_ids=m.message_id)
    except:
        pass

@app.on_message(filters.group | filters.channel)
async def auto_delete(c, m):
    chat_id = str(m.chat.id)
    conf = get_settings(chat_id)
    delay = conf['bot'] if m.from_user and m.from_user.is_bot else conf['user']
    if delay > 0:
        asyncio.create_task(schedule_deletion(c, m, delay))

@server.route('/set_ping', methods=['POST'])
def set_ping():
    data = request.json or {}
    global PING_URL, PING_INTERVAL
    if 'url' in data:
        PING_URL = data['url']
    if 'interval' in data:
        PING_INTERVAL = int(data['interval'])
    return jsonify({"PING_URL": PING_URL, "PING_INTERVAL": PING_INTERVAL})

def start_ping_loop():
    async def loop():
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    await session.get(PING_URL)
                except:
                    pass
                await asyncio.sleep(PING_INTERVAL)
    asyncio.get_event_loop().create_task(loop())

def start_flask():
    server.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))

if __name__ == '__main__':
    start_ping_loop()
    Thread(target=start_flask, daemon=True).start()
    app.run()
