from flask import Flask
from flask_cors import CORS
import certifi
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)
ca = certifi.where()
mongo_client = MongoClient(
    "mongodb+srv://efladmin:god_is_watching@cluster0.eezohvz.mongodb.net/?retryWrites=true&w=majority",
    tlsCAFile=ca
)
db = mongo_client['afc2025']
