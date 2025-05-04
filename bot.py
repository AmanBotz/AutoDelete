import asyncio, os, aiohttp, threading
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, enums

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
PING_URL = os.getenv("PING_URL", "https://example.com")
SESSION_NAME = os.getenv("SESSION_NAME", "autodeleter_bot")

db = AsyncIOMotorClient(MONGO_URI)["autodeleter"]
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
flask_app = Flask(__name__)

@flask_app.route("/")
def home(): return "Running"

async def ping():
    async with aiohttp.ClientSession() as s:
        while True:
            try: await s.get(PING_URL)
            except: pass
            await asyncio.sleep(30)

async def is_admin(chat_id, user_id):
    async for m in app.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
        if m.user.id == user_id: return True
    return False

@app.on_message(filters.command("start") & filters.private)
async def start(c, m):
    await m.reply("Hello! I'm Auto Deleter Bot.\n\nAdd me to your group as admin and use /setdelay <seconds>.")

@app.on_message(filters.command("setdelay") & filters.group)
async def set_delay(c, m):
    if not m.from_user or not await is_admin(m.chat.id, m.from_user.id): return
    try: d = int(m.text.split()[1])
    except: return await m.reply("Usage: /setdelay <seconds>")
    await db.settings.update_one({"chat_id": m.chat.id}, {"$set": {"delay": d}}, upsert=True)
    await m.reply(f"Delay set to {d}s")

@app.on_message(filters.group & ~filters.service)
async def delete_later(c, m):
    d = 5
    s = await db.settings.find_one({"chat_id": m.chat.id})
    if s and "delay" in s: d = s["delay"]
    await asyncio.sleep(d)
    try: await c.delete_messages(m.chat.id, m.id)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=8000)).start()
    async def main():
        asyncio.create_task(ping())
        await app.run()
    asyncio.run(main())
