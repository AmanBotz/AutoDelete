import os
import asyncio
import threading
from flask import Flask
import requests
from pyrogram import Client, filters, enums, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
    await idle()
    await bot.stop()

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_client())

@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Add to Group", url=f"t.me/{client.me.username}?startgroup=true"),
        InlineKeyboardButton("List Chats", callback_data="list_chats")
    ]])
    await message.reply("**Auto-Delete Bot**\nConfigure deletion delays:", reply_markup=keyboard)

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
        [InlineKeyboardButton(unit, callback_data=f"unit {target} {unit}") for unit in ["seconds", "minutes", "hours", "days", "weeks"]],
        [InlineKeyboardButton("⏮ Cancel", callback_data="cancel")]
    ])
    await query.message.edit("Select time unit:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^unit"))
async def set_unit(client, query: CallbackQuery):
    _, target, unit = query.data.split()
    chat = await get_chat(query.message.chat.id)
    default = 3 if target == "user_msg" else 120
    current = chat.get(f"{target}_delay", default)
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
    default = 3 if target == "user_msg" else 120
    current = chat.get(f"{target}_delay", default)
    delta = 1 if direction == "+1" else -1
    multiplier = {"seconds":1,"minutes":60,"hours":3600,"days":86400,"weeks":604800}[unit]
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
        try:
            member = await update.chat.get_member(update.from_user.id)
            if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                return
        except:
            return
        perms = await update.chat.get_member((await client.get_me()).id)
        if not perms.privileges.can_delete_messages:
            await client.send_message(update.chat.id, "⚠️ Please grant me message deletion permissions!")
            return
        await update_chat(update.chat.id, {"user_msg_delay": 3, "bot_msg_delay": 120})
        await client.send_message(update.from_user.id, f"Bot added to {update.chat.title}\nConfigure with /settings")

@app.route('/')
def home():
    return "Bot Running"

@app.route('/ping')
def ping():
    return "PONG"

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=ping_server, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)
