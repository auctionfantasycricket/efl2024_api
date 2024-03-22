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
        (20 * (15 - owner_items["totalCount"] - 1))

    role = updated_data["player_role"]
    if role == "Batter":
        owner_items["batCount"] += 1
    elif role == "Bowler":
        owner_items["ballCount"] += 1
    elif role == "All-Rounder":
        owner_items["arCount"] += 1
    elif role == "WK Keeper - Batter":
        owner_items["batCount"] += 1
        owner_items["wkCount"] += 1
    else:
        print("Role not found")

    if updated_data["country"] != "India":
        owner_items["fCount"] += 1

    return owner_items


@app.route('/deleteplayer/<_id>', methods=['PUT'])
def delete_player(_id):
    # Retrieve delete data from request JSON
    delete_data = request.get_json()

    # Filter to identify the player to delete
    id_filter = {"_id": ObjectId(_id)}

    # Update player data to reset boughtFor and ownerName
    update_data = {
        "$set": {
            "boughtFor": 0,
            "ownerTeam": "",
            "status":"unsold"
        }
    }
# Get the collectionName from the query parameter
    collection_name = request.args.get(
        'collectionName', 'efl_playersCentral_test')

    collection = db[collection_name]
    # Update player in the collection
    result = collection.update_one(id_filter, update_data)

    # Retrieve necessary fields from delete data
    amount = delete_data.get("boughtFor", 0)
    owner_team = delete_data.get("ownerTeam", "")

    # Query to find owner's data
    owner_query = {"teamName": owner_team}
    ownercollection = request.args.get(
        'ownerCollectionName', 'efl_ownerTeams_test')

    ownercollection = db[ownercollection]
    owners_data = ownercollection.find(owner_query)

    for owner_items in owners_data:
        # Adjust owner's current purse and total count
        owner_items["currentPurse"] += int(amount)
        owner_items["totalCount"] -= 1

        # Adjust max bid based on total count
        owner_items["maxBid"] = owner_items["currentPurse"] - \
            (20 * (15 - owner_items["totalCount"]-1))

        # Adjust specific count based on player's role
        role = delete_data.get("player_role", "")
        if role == "Batter":
            owner_items["batCount"] -= 1
        elif role == "Bowler":
            owner_items["ballCount"] -= 1
        elif role == "All-Rounder":
            owner_items["arCount"] -= 1
        elif role == "WK Keeper - Batter":
            owner_items["batCount"] -= 1
            owner_items["wkCount"] -= 1

        # Adjust foreign player count if necessary
        if delete_data.get("country", "") != "India":
            owner_items["fCount"] -= 1

        # Update owner data in the collection
        filter_owner = {"_id": owner_items["_id"]}
        ownercollection.update_one(
            filter_owner, {"$set": owner_items})

    # Return the result of updating the player
    return json_util.dumps(result.raw_result)


def calculate_batting_points(batting_stats):
    runs = batting_stats['runs']
    fours = batting_stats['fours']
    sixes = batting_stats['sixes']
    strike_rate = batting_stats['sr']

    points = runs + fours + (2 * sixes)

    if runs >= 100:
        points += 16
    elif runs >= 50:
        points += 8
    elif runs >= 30:
        points += 4

    if 170 < strike_rate:
        points += 6
    elif 150.01 <= strike_rate <= 170:
        points += 4
    elif 130 <= strike_rate < 150:
        points += 2
    elif 50 <= strike_rate <= 59.99:
        points -= 4
    elif strike_rate < 50:
        points -= 6

    return points


def calculate_bowling_points(bowling_stats):
    wickets = bowling_stats['wickets']
    # Assuming maiden_overs is provided
    maiden_overs = bowling_stats.get('maiden_overs', 0)
    economy = bowling_stats.get('economy', 7.1)  # Assuming economy is provided

    points = 25 * wickets

    if wickets >= 5:
        points += 16
    elif wickets == 4:
        points += 8
    elif wickets == 3:
        points += 4

    points += 12 * maiden_overs

    if economy < 5:
        points += 6
    elif 5 <= economy <= 5.99:
        points += 4
    elif 6 <= economy <= 7:
        points += 2
    elif 10 <= economy <= 11:
        points -= 2
    elif 11.01 <= economy <= 12:
        points -= 4
    elif economy > 12:
        points -= 6

    return points


def calculate_fielding_points(fielding_stats):
    catches = fielding_stats['catches']
    runouts = fielding_stats['runouts']
    stumpings = fielding_stats['stumpings']

    points = 8 * catches

    if catches >= 3:
        points += 4

    points += 12 * stumpings
    points += 8 * runouts

    return points


def calculate_total_points(player):
    batting_points = calculate_batting_points(player['batting'])
    bowling_points = calculate_bowling_points(player['bowling'])
    fielding_points = calculate_fielding_points(player['fielding'])

    total_points = batting_points + bowling_points + fielding_points

    return {
        'playername': player['player_name'],
        'batting points': batting_points,
        'bowling points': bowling_points,
        'fielding points': fielding_points,
        'total_points': total_points
    }


def calculate_points_for_players(players):
    result = []
    for player in players:
        result.append(calculate_total_points(player))
    return result


if __name__ == '__main__':
    # Run the Flask app on http://127.0.0.1:5000/
    '''
    players = [
        {
            'player_name': 'Ravindra Jadeja',
            'batting': {'runs': 32, 'fours': 3, 'sixes': 3, 'sr': 123.44},  # 45
            'bowling': {'wickets': 2, 'maiden_overs': 1, 'economy': 4.2},  # 66
            # 24+12 = 36
            'fielding': {'catches': 2, 'runouts': 1, 'stumpings': 1}
        }
    ]    
    print(calculate_points_for_players(players))
    '''
    app.run()
