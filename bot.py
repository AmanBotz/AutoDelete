import os
import logging
import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from starlette.requests import Request
from motor.motor_asyncio import AsyncIOMotorClient

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

# Environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
PING_URL = os.getenv("PING_URL")
ADMIN_LOG_CHAT = int(os.getenv("ADMIN_LOG_CHAT", 0))  # optional admin notifications

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# FastAPI for healthchecks & metrics
api = FastAPI()

@api.get("/")
async def health(request: Request):
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

# Pyrogram client
bot = Client("autodelete_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB async client
db = AsyncIOMotorClient(MONGO_URI).autodelete
chats = db.chats    # stores chat configs: { _id, title, admins, user_delay, bot_delay }
state = db.state    # per-user UI state: { _id: user_id, current_chat: chat_id }

# APScheduler for deletion tasks
scheduler = AsyncIOScheduler()

# Decorator for error handling
def safe_handler(fn):
    async def wrapper(client, update):
        try:
            await fn(client, update)
        except Exception as e:
            logger.exception("Error in handler %s", fn.__name__)
            if ADMIN_LOG_CHAT:
                await client.send_message(ADMIN_LOG_CHAT, f"<b>Error:</b> {e}\nHandler: {fn.__name__}")
    return wrapper

# Utilities
def parse_duration(code: str) -> int:
    unit = code[-1]
    val = int(code[:-1])
    mul = dict(s=1, m=60, h=3600, d=86400, w=604800, M=2592000, y=31536000).get(unit)
    return val * mul if mul else 0

async def schedule_delete(message, delay: int):
    run_time = datetime.now(timezone.utc).timestamp() + delay
    scheduler.add_job(lambda: asyncio.create_task(message.delete()), trigger="date", run_date=run_time)

# Bot event handlers
@bot.on_message(filters.private & filters.command("start"))
@safe_handler
async def on_start(client: Client, message: Message):
    await state.update_one({"_id": message.from_user.id}, {"$set": {"current_chat": None}}, upsert=True)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{client.me.username}?startgroup=start")],
        [InlineKeyboardButton("➕ Add to Channel", url=f"https://t.me/{client.me.username}?startchannel=start")],
        [InlineKeyboardButton("📂 My Chats", callback_data="list_chats")]
    ])
    await message.reply("Welcome! Use buttons to configure auto-delete.", reply_markup=kb)

@bot.on_callback_query(filters.regex("list_chats"))
@safe_handler
async def on_list(client: Client, cb: CallbackQuery):
    user_id = cb.from_user.id
    docs = chats.find({"admins": user_id})
    buttons = []
    async for c in docs:
        buttons.append([InlineKeyboardButton(c.get("title", str(c["_id"])), callback_data=f"select_{c['_id']}")])
    if not buttons:
        return await cb.answer("No admin chats found.")
    await cb.message.edit("Select chat:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex(r"select_"))
@safe_handler
async def on_select(client: Client, cb: CallbackQuery):
    user_id = cb.from_user.id
    chat_id = int(cb.data.split("_",1)[1])
    await state.update_one({"_id": user_id}, {"$set": {"current_chat": chat_id}}, upsert=True)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Show Settings", callback_data="show_settings")],
        [InlineKeyboardButton("User Delay", callback_data="set_user")],
        [InlineKeyboardButton("Bot Delay", callback_data="set_bot")],
        [InlineKeyboardButton("Reset", callback_data="reset")],
        [InlineKeyboardButton("Back", callback_data="list_chats")]
    ])
    await cb.message.edit(f"Configuring <b>{chat_id}</b>", reply_markup=kb)

@bot.on_callback_query(filters.regex("show_settings"))
@safe_handler
async def on_show(client: Client, cb: CallbackQuery):
    user_id = cb.from_user.id
    st = await state.find_one({"_id": user_id})
    cid = st.get("current_chat")
    doc = await chats.find_one({"_id": cid})
    ud = doc.get("user_delay", 0)
    bd = doc.get("bot_delay", 0)
    await cb.answer(f"User: {ud}s, Bot: {bd}s", show_alert=True)

@bot.on_callback_query(filters.regex(r"set_(user|bot)"))
@safe_handler
async def on_set_menu(client: Client, cb: CallbackQuery):
    choices = ["10s","1m","5m","1h","1d","1w","1M","1y"]
    typ = cb.data.split("_")[1]
    buttons = [[InlineKeyboardButton(c, callback_data=f"delay_{typ}_{c}") for c in choices[i:i+4]] for i in range(0,len(choices),4)]
    buttons.append([InlineKeyboardButton("Back", callback_data="list_chats")])
    await cb.message.edit("Choose delay:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex(r"delay_(user|bot)_"))
@safe_handler
async def on_set_delay(client: Client, cb: CallbackQuery):
    user_id = cb.from_user.id
    typ, dur = cb.data.split("_")[1:]
    st = await state.find_one({"_id": user_id})
    cid = st.get("current_chat")
    sec = parse_duration(dur)
    field = "user_delay" if typ=="user" else "bot_delay"
    await chats.update_one({"_id": cid}, {"$set": {field: sec}}, upsert=True)
    await cb.message.edit(f"Set {typ} delay to {dur}")

@bot.on_callback_query(filters.regex("reset"))
@safe_handler
async def on_reset(client: Client, cb: CallbackQuery):
    user_id = cb.from_user.id
    cid = (await state.find_one({"_id": user_id})).get("current_chat")
    await chats.update_one({"_id": cid}, {"$unset": {"user_delay":"","bot_delay":""}})
    await cb.message.edit("Settings reset.")

@bot.on_chat_member_updated()
@safe_handler
async def on_chat_change(client: Client, update):
    chat_id = update.chat.id
    user = update.new_chat_member.user
    if user.id == client.me.id and update.new_chat_member.status == ChatMemberStatus.MEMBER:
        chat = await client.get_chat(chat_id)
        admins = [m.user.id async for m in client.get_chat_members(chat_id, filter="administrators")]
        await chats.update_one({"_id": chat_id}, {"$set": {"title": chat.title, "admins": admins}}, upsert=True)
    elif user.id == client.me.id and update.new_chat_member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        await chats.delete_one({"_id": chat_id})

@bot.on_message(filters.group | filters.channel)
@safe_handler
async def on_message(bot, message: Message):
    cid = message.chat.id
    cfg = await chats.find_one({"_id": cid}) or {}
    me = await bot.get_me()
    delay = cfg.get("bot_delay" if message.from_user.id==me.id else "user_delay", 0)
    if delay>0:
        await schedule_delete(message, delay)

# Startup
async def start_all():
    scheduler.start()
    # health pinger
    async def ping_loop():
        import httpx
        while True:
            try:
                await httpx.get(PING_URL)
            except:
                pass
            await asyncio.sleep(30)
    asyncio.create_task(ping_loop())
    # run FastAPI separately (e.g. with uvicorn)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_all())
    bot.run()
