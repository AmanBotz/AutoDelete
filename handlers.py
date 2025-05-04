from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import set_group_delay
from deleter import queue_message

@Client.on_message(filters.group & filters.text & ~filters.bot)
async def handle_user_message(client, message: Message):
    await queue_message(message)

@Client.on_message(filters.group & filters.command("setdelay") & filters.user())
async def set_delay(client, message: Message):
    if not message.from_user:
        return
    user = message.from_user
    member = await client.get_chat_member(message.chat.id, user.id)
    if member.can_delete_messages:
        try:
            delay = int(message.text.split(" ", 1)[1])
            set_group_delay(message.chat.id, delay)
            await message.reply(f"Delay set to {delay} seconds.")
        except:
            await message.reply("Usage: /setdelay <seconds>")
    else:
        await message.reply("You need delete messages permission.")
