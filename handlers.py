from pyrogram import Client, filters
from pyrogram.types import Message
from database import set_group_delay
from deleter import queue_message

@Client.on_message(filters.group & filters.text & ~filters.bot)
async def handle_user_message(client, message: Message):
    print(f"Got user message in chat {message.chat.id} from {message.from_user.id}")
    await queue_message(message)

@Client.on_message(filters.command("setdelay") & filters.group)
async def set_delay(client, message: Message):
    user = message.from_user
    if not user:
        return

    try:
        member = await client.get_chat_member(message.chat.id, user.id)
        if not member.can_delete_messages:
            await message.reply("You need delete message permission.")
            return

        delay = int(message.text.split(" ", 1)[1])
        set_group_delay(message.chat.id, delay)
        await message.reply(f"Set delete delay to {delay} seconds.")
    except Exception as e:
        print("Error in set_delay:", e)
        await message.reply("Usage: /setdelay <seconds>")
