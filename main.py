import asyncio
from flask import Flask
from threading import Thread

from bot import bot
from deleter import process_queue
from pinger import keep_alive
import handlers  # Important: must be imported AFTER `bot` is created

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive."

def run_flask():
    app.run(host="0.0.0.0", port=8000)

async def start_all():
    Thread(target=run_flask).start()
    await bot.start()
    me = await bot.get_me()
    print(f"Bot started as @{me.username}")
    asyncio.create_task(process_queue())
    asyncio.create_task(keep_alive())

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(start_all())
