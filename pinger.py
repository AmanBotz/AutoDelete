import asyncio
import aiohttp
from config import PING_URL

async def keep_alive():
    while True:
        if PING_URL:
            try:
                async with aiohttp.ClientSession() as session:
                    await session.get(PING_URL)
                    print("Pinged URL")
            except Exception as e:
                print("Ping failed:", e)
        await asyncio.sleep(30)
