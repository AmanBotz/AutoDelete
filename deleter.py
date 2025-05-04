import asyncio
from pyrogram.types import Message
from config import DELETE_DELAY_DEFAULT
from database import get_group_delay

queue = asyncio.Queue()

async def queue_message(msg: Message):
    await queue.put(msg)

async def process_queue():
    while True:
        msg = await queue.get()
        try:
            delay = get_group_delay(msg.chat.id) or DELETE_DELAY_DEFAULT
            await asyncio.sleep(delay)
            await msg.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")
        queue.task_done()
