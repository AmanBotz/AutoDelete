import os
import asyncio
from threading import Thread
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatMemberUpdated
)
from flask import Flask, request, jsonify
from pymongo import MongoClient
import aiohttp

# Environment
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
PING_URL = os.getenv("PING_URL")
PING_INTERVAL = int(os.getenv("PING_INTERVAL", 30))

# MongoDB
mongo = MongoClient(MONGO_URI)
db = mongo['auto_delete_bot']
settings_col = db['settings']
chats_col = db['chats']
user_ctx = db['user_context']

# Pyrogram & Flask
app = Client("auto_delete_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
server = Flask(__name__)

def get_settings(chat_id: str):
    doc = settings_col.find_one({"_id": chat_id})
    return {"user": doc.get("user", 0), "bot": doc.get("bot", 0)} if doc else {"user": 0, "bot": 0}

def set_settings(chat_id: str, user_delay=None, bot_delay=None):
    update = {}
    if user_delay is not None: update['user'] = user_delay
    if bot_delay is not None: update['bot'] = bot_delay
    settings_col.update_one({"_id": chat_id}, {"$set": update}, upsert=True)

def parse_delay(text: str) -> int:
    num = int(text[:-1])
    unit = text[-1]
    if unit == 's': return num
    if unit == 'm': return num * 60
    if unit == 'h': return num * 3600
    if unit == 'd': return num * 86400
    if unit == 'w': return num * 7 * 86400
    if unit == 'M': return num * 30 * 86400
    if unit == 'y': return num * 365 * 86400
    raise ValueError

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    bot = await c.get_me()
    buttons = [
        [InlineKeyboardButton("➕ Add to a Group", url=f"https://t.me/{bot.username}?startgroup=true")],
        [InlineKeyboardButton("➕ Add to a Channel", url=f"https://t.me/{bot.username}?startchannel=true")],
        [InlineKeyboardButton("📋 List my Chats", callback_data="listchats")]
    ]
    text = (
        "👋 Welcome! I'm AutoDelete Bot.\n"
        "• I remove user and bot messages after a delay you set.\n"
        "• Supported units: s=seconds, m=minutes, h=hours, d=days, w=weeks, M=months, y=years.\n"
        "• In private chat, list and select a chat via the button, then configure with /setdelay_user or /setdelay_bot."
    )
    await m.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_chat_member()
async def on_my_chat_member(c, chat_member: ChatMemberUpdated):
    if chat_member.new_chat_member.status in ["member", "administrator"]:
        chat_id = str(chat_member.chat.id)
        title = chat_member.chat.title or chat_member.chat.username or chat_id
        chats_col.update_one({"_id": chat_id}, {"$set": {"title": title, "username": chat_member.chat.username}}, upsert=True)
        button = InlineKeyboardMarkup([[InlineKeyboardButton("⚙ Configure this chat", callback_data=f"select_{chat_id}")]])
        await c.send_message(chat_id, f"🤖 I've been added to **{title}**. Configure delays now:", reply_markup=button, parse_mode="Markdown")
        adder = chat_member.from_user
        if adder:
            try:
                await c.send_message(adder.id, f"👋 You added me to **{title}**. Use 'List my Chats' in /start to configure.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 List my Chats", callback_data="listchats")]]), parse_mode="Markdown")
            except:
                pass

@app.on_callback_query()
async def handle_cb(c, cb: CallbackQuery):
    data = cb.data; user_id = str(cb.from_user.id)
    if data == "listchats":
        chats = list(chats_col.find({}))
        if not chats:
            return await cb.answer("No chats found. Send a message in your group/channel.", show_alert=True)
        kb = [[InlineKeyboardButton(ch.get('title') or ch['_id'], callback_data=f"select_{ch['_id']}")] for ch in chats]
        await cb.message.edit("Select a chat to configure:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("select_"):
        chat_id = data.split("_")[1]
        user_ctx.update_one({"_id": user_id}, {"$set": {"chat_id": chat_id}}, upsert=True)
        await cb.message.edit(f"✅ Selected chat: **{chat_id}**\nNow send /setdelay_user or /setdelay_bot in this private chat.", parse_mode="Markdown")

@app.on_message(filters.command(["setdelay_user", "setdelay_bot"]) & filters.private)
async def set_delay_pm(c, m):
    user_id = str(m.from_user.id)
    ctx = user_ctx.find_one({"_id": user_id})
    if not ctx or 'chat_id' not in ctx:
        return await m.reply("⚠️ No chat selected. Tap 'List my Chats' first.", parse_mode="Markdown")
    chat_id = ctx['chat_id']; cmd = m.command[0]; arg = m.command[1] if len(m.command)>1 else None
    try: delay = parse_delay(arg)
    except: return await m.reply(f"🚫 Invalid. Usage: /{cmd} <number><unit>, e.g. /{cmd} 2w")
    if cmd=="setdelay_user": set_settings(chat_id, user_delay=delay)
    else: set_settings(chat_id, bot_delay=delay)
    await m.reply(f"✅ `{cmd}` for **{chat_id}**: delete after {arg}.", parse_mode="Markdown")

async def schedule_deletion(c, m, delay):
    await asyncio.sleep(delay)
    try: await c.delete_messages(chat_id=m.chat.id, message_ids=m.message_id)
    except: pass

@app.on_message(filters.group | filters.channel)
async def auto_delete(c, m):
    chats_col.update_one({"_id": str(m.chat.id)}, {"$set": {"title": m.chat.title, "username": m.chat.username}}, upsert=True)
    conf = get_settings(str(m.chat.id))
    delay = conf['bot'] if m.from_user and m.from_user.is_bot else conf['user']
    if delay>0: asyncio.create_task(schedule_deletion(c, m, delay))

@server.route('/set_ping', methods=['POST'])
def set_ping():
    data = request.json or {}
    global PING_URL, PING_INTERVAL
    if 'url' in data: PING_URL = data['url']
    if 'interval' in data: PING_INTERVAL = int(data['interval'])
    return jsonify({"PING_URL": PING_URL, "PING_INTERVAL": PING_INTERVAL})

def start_ping_loop():
    async def loop():
        async with aiohttp.ClientSession() as session:
            while True:
                try: await session.get(PING_URL)
                except: pass
                await asyncio.sleep(PING_INTERVAL)
    asyncio.get_event_loop().create_task(loop())

def start_flask():
    server.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))

if __name__ == '__main__':
    start_ping_loop()
    Thread(target=start_flask, daemon=True).start()
    app.run()
