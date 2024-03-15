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


@app.route('/updateplayer/<_id>', methods=['PUT'])
def update_player(_id):
    updated_data = request.get_json()
    filter = {"_id": ObjectId(str(_id))}
    # Get the collectionName from the query parameter
    collection_name = request.args.get(
        'collectionName', 'efl_playersCentral_test')

    collections = db[collection_name]
    # Get the collectionName from the query parameter

    # Exclude _id from update_data to avoid updating it
    updated_data.pop('_id', None)
    result = collections.update_one(filter, {"$set": updated_data})

    if updated_data['status'] == "sold":
        ownercollection = request.args.get(
            'ownerCollectionName', 'efl_ownerTeams_test')

        ownercollection = db[ownercollection]
        update_owner_data(updated_data, ownercollection)

    return json_util.dumps(result.raw_result)


def update_owner_data(updated_data, ownercollection):
    owner_team = updated_data['ownerTeam']
    myquery = {"teamName": owner_team}
    owners_data = ownercollection.find(myquery)

    for owner_items in owners_data:
        owner_items = update_owner_items(owner_items, updated_data)
        filter_owner = {"_id": ObjectId(str(owner_items["_id"]))}
        ownercollection.update_one(filter_owner, {"$set": owner_items})


def update_owner_items(owner_items, updated_data):
    owner_items["currentPurse"] -= int(updated_data["boughtFor"])
    owner_items["totalCount"] += 1
    owner_items["maxBid"] = owner_items["currentPurse"] - \
        (20 * (15 - owner_items["totalCount"]))

    role = updated_data["player_role"]
    if role == "Batter":
        owner_items["batCount"] += 1
    elif role == "Bowler":
        owner_items["ballCount"] += 1
    elif role == "All-Rounder":
        owner_items["arCount"] += 1
    elif role == "WK Kepper - Batter":
        owner_items["batCount"] += 1
        owner_items["wkCount"] += 1
    else:
        print("Role not found")

    if updated_data["country"] != "India":
        owner_items["fCount"] += 1

    return owner_items


if __name__ == '__main__':
    # Run the Flask app on http://127.0.0.1:5000/
    app.run()
