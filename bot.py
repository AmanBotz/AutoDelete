import os
import asyncio
import threading
import requests
from flask import Flask
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient

app = Flask(__name__)
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
PING_URL = os.environ["PING_URL"]

bot = Client("auto_delete_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo.auto_delete_bot

async def get_chat(chat_id):
    return await db.chats.find_one({"chat_id": chat_id})

async def update_chat(chat_id, data):
    await db.chats.update_one({"chat_id": chat_id}, {"$set": data}, upsert=True)

async def delete_message(chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except:
        pass

def ping_server():
    while True:
        try:
            requests.get(PING_URL)
        except:
            pass
        threading.Event().wait(30)

async def run_client():
    await bot.start()
    await bot.idle()

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_client())

@bot.on_message(filters.command("start"))
async def start(_, message: Message):
    me = await bot.get_me()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Add to Group", url=f"https://t.me/{me.username}?startgroup=true")],
        [InlineKeyboardButton("Settings", callback_data="settings")]
    ])
    await message.reply("Auto-Delete Bot\nConfigure deletion delays:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^settings$"))
async def settings(_, query: CallbackQuery):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("User Messages", callback_data="set_delay user_msg")],
        [InlineKeyboardButton("Bot Messages", callback_data="set_delay bot_msg")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    await query.message.edit("Select option:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^set_delay"))
async def set_delay(_, query: CallbackQuery):
    _, target = query.data.split()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(u, callback_data=f"set_unit {target} {u}") for u in ["seconds","minutes","hours","days","weeks"]],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])
    await query.message.edit("Select time unit:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^set_unit"))
async def set_unit(_, query: CallbackQuery):
    _, target, unit = query.data.split()
    chat = await get_chat(query.message.chat.id) or {}
    key = f"{target}_delay"
    current = chat.get(key, 3 if target == "user_msg" else 120)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"-1 {unit}", callback_data=f"adjust {target} {unit} -1"),
            InlineKeyboardButton(f"+1 {unit}", callback_data=f"adjust {target} {unit} +1")
        ],
        [InlineKeyboardButton(f"Current: {current} sec", callback_data="none")],
        [
            InlineKeyboardButton("Confirm", callback_data=f"confirm {target} {unit}"),
            InlineKeyboardButton("Cancel", callback_data="cancel")
        ]
    ])
    await query.message.edit("Adjust delay:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^adjust"))
async def adjust(_, query: CallbackQuery):
    _, target, unit, direction = query.data.split()
    chat_id = query.message.chat.id
    chat = await get_chat(chat_id) or {}
    key = f"{target}_delay"
    current = chat.get(key, 3 if target == "user_msg" else 120)
    multiplier = {"seconds":1,"minutes":60,"hours":3600,"days":86400,"weeks":604800}[unit]
    new = max(1, current + int(direction) * multiplier)
    await update_chat(chat_id, {key: new})
    await set_unit(_, query)

@bot.on_callback_query(filters.regex(r"^confirm"))
async def confirm(_, query: CallbackQuery):
    await query.message.edit("Delay updated!")

@bot.on_callback_query(filters.regex(r"^cancel"))
async def cancel(_, query: CallbackQuery):
    await query.message.delete()

@bot.on_message(filters.group | filters.channel)
async def track(_, message: Message):
    chat = await get_chat(message.chat.id)
    if not chat:
        return
    if message.from_user and message.from_user.is_bot:
        delay = chat.get("bot_msg_delay", 120)
    else:
        delay = chat.get("user_msg_delay", 3)
    asyncio.create_task(delete_message(message.chat.id, message.id, delay))

@bot.on_chat_member_updated()
async def chat_member(_, update):
    if update.new_chat_member and update.new_chat_member.user.id == (await bot.get_me()).id:
        try:
            member = await update.chat.get_member(update.from_user.id)
            if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                return
        except:
            return
        perms = await update.chat.get_member((await bot.get_me()).id)
        if not perms.privileges.can_delete_messages:
            await bot.send_message(update.chat.id, "⚠️ Please grant me message deletion permissions!")
            return
        await update_chat(update.chat.id, {"user_msg_delay": 3, "bot_msg_delay": 120})
        await bot.send_message(update.from_user.id, f"Bot added to {update.chat.title}\nConfigure with /settings")

@app.route("/")
def home():
    return "Bot Running"

@app.route("/ping")
def ping():
    return "PONG"

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=ping_server, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
