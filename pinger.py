import asyncio
import aiohttp
from config import PING_URL

async def keep_alive():
    while True:
        if PING_URL:
            try:
                async with aiohttp.ClientSession() as session:
                    await session.get(PING_URL)
            except Exception as e:
                print(f"Ping failed: {e}")
        await asyncio.sleep(30)
