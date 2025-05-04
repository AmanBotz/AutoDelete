import os
import asyncio
from flask import Flask, jsonify
import aiohttp
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, types
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
MONGO_URI = os.environ["MONGO_URI"]
PING_URL = os.environ.get("PING_URL")

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo.bot_db
chats = db.chats  # stores {chat_id, user_delay, bot_delay}

def default_settings():
    return {"user_delay": 3, "bot_delay": 120}

app = Flask(__name__)

@app.route("/")
def ping():
    return jsonify({"status": "ok"})

async def ping_loop():
    if not PING_URL:
        return
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await session.get(PING_URL)
            except:
                pass
            await asyncio.sleep(30)

bot = Client("auto_delete_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

@bot.on_chat_member()  # when bot is added to a chat
async def welcome_bot(client, chat_member):
    if chat_member.new_chat_member.user.id == (await client.get_me()).id:
        chat = chat_member.chat
        perms = await client.get_chat(chat.id)
        if not perms.can_delete_messages:
            await client.send_message(chat.id, "⚠️ Grant me Delete Messages permission! I cannot function without it.")
        await chats.update_one(
            {"chat_id": chat.id},
            {"$setOnInsert": {**default_settings(), "chat_id": chat.id}},
            upsert=True
        )
        await client.send_message(chat.id, "✅ Auto-delete enabled with default delays.")

@bot.on_message(filters.group | filters.channel)
async def schedule_delete(client, message):
    cfg = await chats.find_one({"chat_id": message.chat.id}) or default_settings()
    delay = cfg["bot_delay"] if message.from_user.id == (await client.get_me()).id else cfg["user_delay"]
    asyncio.create_task(delete_after(message, delay))

async def delete_after(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

@bot.on_message(filters.private & filters.command("start"))
async def start(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Group/Channel", url=f"https://t.me/{(await client.get_me()).username}?startgroup=true")],
        [InlineKeyboardButton("📋 List Chats", callback_data="list_chats")],
        [InlineKeyboardButton("⏱️ Set Delay", callback_data="set_delay")]
    ])
    await message.reply("Welcome! Manage your auto-delete settings here:", reply_markup=kb)

@bot.on_callback_query()
async def callbacks(client, cq):
    data = cq.data
    if data == "list_chats":
        docs = chats.find({})
        text = "Tracked Chats:\n"
        async for d in docs:
            text += f"• {d['chat_id']} (user: {d['user_delay']}s, bot: {d['bot_delay']}s)\n"
        await cq.answer(text, show_alert=True)
    elif data == "set_delay":
        docs = chats.find({})
        buttons = []
        async for d in docs:
            buttons.append([InlineKeyboardButton(str(d['chat_id']), callback_data=f"cfg:{d['chat_id']}")])
        await cq.message.edit("Select chat:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("cfg:"):
        chat_id = int(data.split(':')[1])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("User Msg Delay", callback_data=f"set:u:{chat_id}"), InlineKeyboardButton("Bot Msg Delay", callback_data=f"set:b:{chat_id}")]
        ])
        await cq.message.edit("Choose setting to change:", reply_markup=kb)
    elif data.startswith("set:"):
        _, typ, chat_id = data.split(':')
        units = ['s','m','h','d','w','mo','y']
        buttons = [[InlineKeyboardButton(u, callback_data=f"upd:{typ}:{chat_id}:{u}:0") for u in units]]
        buttons.append([InlineKeyboardButton("+1", callback_data=f"chg:{typ}:{chat_id}:1"), InlineKeyboardButton("-1", callback_data=f"chg:{typ}:{chat_id}:-1")])
        await cq.message.edit("Select unit and adjust:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("chg:"):
        _, typ, chat_id, delta = data.split(':')
        chat_id = int(chat_id); delta = int(delta)
        key = 'user_delay' if typ=='u' else 'bot_delay'
        doc = await chats.find_one({"chat_id": chat_id})
        current = doc[key]
        new = max(1, current + delta)
        await chats.update_one({"chat_id": chat_id}, {"$set": {key: new}})
        await cq.answer(f"Set {key} to {new}")
    await cq.answer()

async def main():
    loop = asyncio.get_event_loop()
    loop.create_task(ping_loop())
    bot_task = bot.start()
    flask_task = asyncio.to_thread(app.run, host='0.0.0.0', port=int(os.environ.get('PORT',8080)))
    await asyncio.gather(bot_task, flask_task)

if __name__ == '__main__':
    asyncio.run(main())
