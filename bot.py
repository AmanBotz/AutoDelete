import os
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import aiohttp

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
PING_URL = os.environ.get("PING_URL")

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["telegram_bot"]
chats_collection = db["chats"]

flask_app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

@flask_app.route("/")
def home():
    return "Bot is running"

async def ping():
    async with aiohttp.ClientSession() as session:
        try:
            await session.get(PING_URL)
        except:
            pass

scheduler.add_job(ping, "interval", seconds=30)

def get_delay_buttons():
    units = ["seconds", "minutes", "hours", "days", "weeks", "months", "years"]
    buttons = [[InlineKeyboardButton(unit.capitalize(), callback_data=f"unit_{unit}")] for unit in units]
    buttons.append([
        InlineKeyboardButton("+1", callback_data="increment"),
        InlineKeyboardButton("-1", callback_data="decrement")
    ])
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.private & filters.command("start"))
async def start(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Add to Group", url=f"https://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("List Chats", callback_data="list_chats")],
        [InlineKeyboardButton("User Msg Delay", callback_data="set_user_delay")],
        [InlineKeyboardButton("Bot Msg Delay", callback_data="set_bot_delay")]
    ])
    await message.reply("Welcome to the Auto-Delete Bot.", reply_markup=keyboard)

@app.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    user_data = await db["users"].find_one({"user_id": user_id}) or {"user_id": user_id, "unit": "seconds", "value": 1}
    if data == "list_chats":
        chats = await chats_collection.find({"user_id": user_id}).to_list(length=None)
        if not chats:
            await callback_query.message.edit_text("No chats found.")
        else:
            text = "\n".join([f"{chat['chat_title']} ({chat['chat_id']})" for chat in chats])
            await callback_query.message.edit_text(f"Your Chats:\n{text}")
    elif data == "set_user_delay":
        await db["users"].update_one({"user_id": user_id}, {"$set": {"setting": "user"}}, upsert=True)
        await callback_query.message.edit_text("Set delay for user messages:", reply_markup=get_delay_buttons())
    elif data == "set_bot_delay":
        await db["users"].update_one({"user_id": user_id}, {"$set": {"setting": "bot"}}, upsert=True)
        await callback_query.message.edit_text("Set delay for bot messages:", reply_markup=get_delay_buttons())
    elif data.startswith("unit_"):
        unit = data.split("_")[1]
        await db["users"].update_one({"user_id": user_id}, {"$set": {"unit": unit}}, upsert=True)
        await callback_query.answer(f"Unit set to {unit}")
    elif data == "increment":
        value = user_data.get("value", 1) + 1
        await db["users"].update_one({"user_id": user_id}, {"$set": {"value": value}}, upsert=True)
        await callback_query.answer(f"Value: {value}")
    elif data == "decrement":
        value = max(1, user_data.get("value", 1) - 1)
        await db["users"].update_one({"user_id": user_id}, {"$set": {"value": value}}, upsert=True)
        await callback_query.answer(f"Value: {value}")

@app.on_chat_member_updated()
async def chat_member_updated(client, chat_member_updated):
    if chat_member_updated.new_chat_member.user.id == client.me.id:
        chat_id = chat_member_updated.chat.id
        chat_title = chat_member_updated.chat.title or "Private Chat"
        user_id = chat_member_updated.from_user.id
        permissions = chat_member_updated.new_chat_member
        can_delete = permissions.can_delete_messages if permissions else False
        await chats_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "chat_title": chat_title, "user_id": user_id}},
            upsert=True
        )
        if not can_delete:
            try:
                await client.send_message(chat_id, "Please grant me permission to delete messages.")
            except:
                pass

@app.on_message(filters.group | filters.channel)
async def handle_messages(client, message):
    chat_id = message.chat.id
    sender_id = message.from_user.id if message.from_user else None
    is_bot = message.from_user.is_bot if message.from_user else False
    user_data = await db["users"].find_one({"user_id": sender_id}) or {}
    unit = user_data.get("unit", "seconds")
    value = user_data.get("value", 1)
    delay = timedelta(**{unit: value})
    if is_bot:
        delay = timedelta(minutes=2)
    elif sender_id == client.me.id:
        delay = timedelta(minutes=2)
    else:
        delay = timedelta(seconds=3)
    await asyncio.sleep(delay.total_seconds())
    try:
        await message.delete()
    except:
        pass

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=8080)).start()
    app.run()
