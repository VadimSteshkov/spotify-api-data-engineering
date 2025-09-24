from pymongo import MongoClient, errors
import json
import time

MONGO_URI = "mongodb://root:example@localhost:27017/?authSource=admin"
DB_NAME = "spotify_db"
#name it same as json files
COLLECTION_NAMES = ["track_playlist", "track_analysis"]

if __name__ == "__main__":
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.server_info()
        print("MongoDB is ready")
    except errors.ServerSelectionTimeoutError:
        raise Exception("MongoDB not reachable after retries")
    db = client[DB_NAME]
    for collection in COLLECTION_NAMES:
        if collection not in db.list_collection_names():
            db.create_collection(collection)
            print(f"Created collection: {collection}")
        if db[collection].count_documents({}) == 0:
            with open(collection + ".json", "r") as f:
                data = json.load(f)
            db[collection].insert_many(data)
            print("Inserted documents")
        else:
            print("Collection already has data, skipping initialization")