from flask import Flask
from flask_cors import CORS
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv
from bson import ObjectId
import os

load_dotenv()
app = Flask(__name__)
CORS(app)
ca = certifi.where()
mongo_client = MongoClient(
    os.getenv("MONGO_URI"),
    tlsCAFile=ca
)
db = mongo_client['afc2026']
try:
    print("Replica Set Name:", mongo_client.admin.command(
        "ismaster")["setName"])
except Exception as e:
    print(f"Error: {e}")

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

DRAFT_LEAGUE_ID = ObjectId('67da30b26a17f44a19c2241a')
AUCTION_LEAGUE_ID = ObjectId('69b8f3329617ab57b73fe0f2')

ASSOCIATE_NATIONS = [
    "Canada", "Namibia", "Nepal", "Netherlands", "Oman",
    "Papua-new-guinea", "Scotland", "Uganda", "United-states-of-america", "Ireland"
]

ESPN_API_BASE = "https://hs-consumer-api.espncricinfo.com/v1/pages/match/details"
