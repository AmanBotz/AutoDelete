import asyncio
from pyrogram.types import Message
from database import get_group_delay
from config import DELETE_DELAY_DEFAULT

queue = asyncio.Queue()

async def queue_message(msg: Message):
    await queue.put(msg)

async def process_queue():
    while True:
        msg = await queue.get()
        try:
            delay = get_group_delay(msg.chat.id) or DELETE_DELAY_DEFAULT
            print(f"Waiting {delay}s to delete message {msg.message_id}")
            await asyncio.sleep(delay)
            await msg.delete()
            print(f"Deleted message {msg.message_id}")
        except Exception as e:
            print(f"Error deleting: {e}")
        queue.task_done()
