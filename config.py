from flask import Flask
from flask_cors import CORS
import certifi
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)
ca = certifi.where()
mongo_client = MongoClient(
    "mongodb+srv://efladmin:god_is_watching@cluster0.eezohvz.mongodb.net/?retryWrites=true&w=majority&replicaSet=atlas-vv2x65-shard-0",
    tlsCAFile=ca
)
db = mongo_client['afc2025']
old_db = mongo_client['afc2024']
try:
    print("Replica Set Name:", mongo_client.admin.command(
        "ismaster")["setName"])
except Exception as e:
    print(f"Error: {e}")
