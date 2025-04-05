from flask import Flask
from flask_cors import CORS
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)
CORS(app)
ca = certifi.where()
mongo_client = MongoClient(
    os.getenv("MONGO_URI"),
    tlsCAFile=ca
)
db = mongo_client['afc2025']
try:
    print("Replica Set Name:", mongo_client.admin.command(
        "ismaster")["setName"])
except Exception as e:
    print(f"Error: {e}")
