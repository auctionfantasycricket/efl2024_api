from flask import Flask, jsonify, request, json, Response
from pymongo import MongoClient
from bson import ObjectId, json_util
from flask_cors import CORS
import certifi
import random
import urllib

app = Flask(__name__)
CORS(app)
ca = certifi.where()
mongo_client = MongoClient(
    "mongodb+srv://efladmin:god_is_watching@cluster0.eezohvz.mongodb.net/?retryWrites=true&w=majority",
    tlsCAFile=ca
)
db = mongo_client['afc2024']

# Define a sample GET API endpoint


@app.route('/sample_api', methods=['GET'])
def get_sample_data():
    # Static JSON data
    sample_data = {
        'message': 'Hello, this is a sample API!',
        'data': [1, 2, 3, 4, 5]
    }

    # Return the JSON response
    return jsonify(sample_data)

# Define a new GET API endpoint that retrieves data from MongoDB based on the collectionName query parameter


@app.route('/get_data', methods=['GET'])
def get_data_from_mongodb():
    # Get the collectionName from the query parameter
    collection_name = request.args.get('collectionName')

    # Check if the collectionName is provided
    if not collection_name:
        return jsonify({'error': 'collectionName is required'}), 400

    # Connect to the MongoDB and retrieve data from the specified collection
    try:

        collection = db[collection_name]
        # You can customize the query as neededß
        data_from_mongo = list(collection.find())
        serialized_data = json_util.dumps(data_from_mongo, default=str)

        #serialized_data = json_util.dumps(data_from_mongo)
        # Deserialize using json_util.loads
        return Response(serialized_data, mimetype="application/json")
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/getspecificplayer', methods=["GET"])
def get_a_player():
    name = request.args.get(
        'playerName', '')
    name = urllib.parse.unquote(name)
    player_query = {"player_name": {"$regex": name, "$options": 'i'}}

    collection_name = request.args.get(
        'collectionName', 'efl_playersCentral_test')
    collection = db[collection_name]
    player_data = collection.find_one(player_query)
    if player_data:
        return json.loads(json_util.dumps(player_data))
    else:
        return json.loads(json_util.dumps("player not found"))


@app.route('/getplayer', methods=["GET"])
def get_player():
    tiers = {1: [], 2: [], 3: [], 4: []}
    # Get the collectionName from the query parameter
    collection_name = request.args.get(
        'collectionName', 'efl_playersCentral_test')

    collection = db[collection_name]

    cursor = collection.find()
    for item in cursor:
        tier = item['tier']
        if tier in tiers and item['status'] == "unsold":
            tiers[tier].append(item)

    pick = None
    for tier in range(1, 5):
        if tiers[tier] and any(player['status'] == 'unsold' for player in tiers[tier]):
            pick = random.choice(
                [player for player in tiers[tier] if player['status'] == 'unsold'])
            break

    if pick is not None:
        return json.loads(json_util.dumps(pick))
    else:
        return json.dumps({"message": "All players are processed"}), 404


if __name__ == '__main__':
    # Run the Flask app on http://127.0.0.1:5000/
    app.run()
