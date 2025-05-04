from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["autodeleter"]
settings = db["group_settings"]

def get_group_delay(chat_id: int) -> int:
    doc = settings.find_one({"chat_id": chat_id})
    return doc["delay"] if doc else None

def set_group_delay(chat_id: int, delay: int):
    settings.update_one({"chat_id": chat_id}, {"$set": {"delay": delay}}, upsert=True)
