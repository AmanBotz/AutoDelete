import os
import asyncio
from threading import Thread
from datetime import datetime, timedelta
from flask import Flask
import requests
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from motor.motor_asyncio import AsyncIOMotorClient

app = Flask(__name__)
API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URI = os.environ.get('MONGO_URI')
PING_URL = os.environ.get('PING_URL')

bot = Client("bot", API_ID, API_HASH, bot_token=BOT_TOKEN)
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo.auto_delete_bot

async def get_chat(chat_id):
    return await db.chats.find_one({"chat_id": chat_id})

async def update_chat(chat_id, data):
    await db.chats.update_one(
        {"chat_id": chat_id},
        {"$set": data},
        upsert=True
    )

async def delete_message(chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except:
        pass

def ping_server():
    try:
        requests.get(PING_URL)
    except:
        pass
    Thread(target=lambda: (
        threading.Event().wait(30),
        ping_server()
    )).start()

@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Add to Group", url=f"t.me/{client.me.username}?startgroup=true"),
        InlineKeyboardButton("List Chats", callback_data="list_chats")
    ]])
    await message.reply("**Auto-Delete Bot**\nConfigure deletion delays:", reply_markup=keyboard)

@bot.on_message(filters.command("help"))
async def help(client, message: Message):
    await message.reply("Configure deletion delays via /settings")

@bot.on_message(filters.command("settings"))
async def settings(client, message: Message):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("User Messages", callback_data="set_delay user_msg"),
        InlineKeyboardButton("Bot Messages", callback_data="set_delay bot_msg")
    ]])
    await message.reply("Configure deletion delays:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^list_chats"))
async def list_chats(client, query: CallbackQuery):
    chats = await db.chats.find().to_list(None)
    text = "**Active Chats:**\n" + "\n".join([f"- `{chat['chat_id']}`" for chat in chats])
    await query.message.edit(text)

@bot.on_callback_query(filters.regex(r"^set_delay"))
async def set_delay(client, query: CallbackQuery):
    target = query.data.split()[1]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(unit, callback_data=f"unit {target} {unit}") for unit in [
            "seconds", "minutes", "hours", "days", "weeks"
        ]],
        [InlineKeyboardButton("⏮ Cancel", callback_data="cancel")]
    ])
    await query.message.edit("Select time unit:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^unit"))
async def set_unit(client, query: CallbackQuery):
    _, target, unit = query.data.split()
    chat = await get_chat(query.message.chat.id)
    current = chat.get(f"{target}_delay", 3 if target == "user_msg" else 120)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"-1 {unit}", callback_data=f"adjust {target} {unit} -1"),
         InlineKeyboardButton(f"+1 {unit}", callback_data=f"adjust {target} {unit} +1")],
        [InlineKeyboardButton(f"Current: {current} sec", callback_data="none")],
        [InlineKeyboardButton("✅ Confirm", callback_data=f"confirm {target} {unit}"),
         InlineKeyboardButton("⏮ Cancel", callback_data="cancel")]
    ])
    await query.message.edit("Adjust delay:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^adjust"))
async def adjust_delay(client, query: CallbackQuery):
    _, target, unit, direction = query.data.split()
    chat = await get_chat(query.message.chat.id)
    current = chat.get(f"{target}_delay", 3 if target == "user_msg" else 120)
    delta = 1 if direction == "+1" else -1
    multiplier = {
        "seconds": 1,
        "minutes": 60,
        "hours": 3600,
        "days": 86400,
        "weeks": 604800
    }[unit]
    new_delay = max(1, current + (delta * multiplier))
    await update_chat(query.message.chat.id, {f"{target}_delay": new_delay})
    await set_unit(client, query)

@bot.on_callback_query(filters.regex(r"^confirm"))
async def confirm_delay(client, query: CallbackQuery):
    await query.message.edit("Delay updated!")

@bot.on_callback_query(filters.regex(r"^cancel"))
async def cancel(client, query: CallbackQuery):
    await query.message.delete()

@bot.on_message(filters.group | filters.channel)
async def track_message(client, message: Message):
    chat = await get_chat(message.chat.id)
    if not chat:
        return
    
    delay = chat["bot_msg_delay"] if message.from_user and message.from_user.is_bot else chat["user_msg_delay"]
    asyncio.create_task(delete_message(message.chat.id, message.id, delay))

@bot.on_chat_member_updated()
async def chat_member_update(client, update):
    if update.new_chat_member and update.new_chat_member.user.id == (await client.get_me()).id:
        chat = update.chat
        try:
            member = await chat.get_member(update.from_user.id)
            if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                return
        except:
            return
        
        perms = await chat.get_member((await client.get_me()).id)
        if not perms.privileges.can_delete_messages:
            await client.send_message(
                chat.id,
                "⚠️ Please grant me message deletion permissions!"
            )
            return
        
        await update_chat(chat.id, {
            "user_msg_delay": 3,
            "bot_msg_delay": 120
        })
        await client.send_message(
            update.from_user.id,
            f"Bot added to {chat.title}\nConfigure with /settings"
        )

@app.route('/')
def home():
    return "Bot Running"

@app.route('/ping')
def ping():
    return "PONG"

if __name__ == "__main__":
    Thread(target=lambda: bot.run()).start()
    Thread(target=ping_server).start()
    app.run(host='0.0.0.0', port=8080)
