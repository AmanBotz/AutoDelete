from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["autodelete_bot"]
settings_col = db["group_settings"]

def get_group_delay(chat_id: int) -> int:
    data = settings_col.find_one({"chat_id": chat_id})
    return data["delay"] if data else None

def set_group_delay(chat_id: int, delay: int):
    settings_col.update_one({"chat_id": chat_id}, {"$set": {"delay": delay}}, upsert=True)
