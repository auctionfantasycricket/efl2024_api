from flask import jsonify, request, json, Response
from pymongo import UpdateOne, DESCENDING
from bson import ObjectId, json_util
import random
import urllib
import requests
from datetime import datetime, timezone, timedelta
from config import app, db  # Import the app from the config module
from draftapi import draftapi_bp  # Import the Blueprint
from liveupdates import liveupdates_bp
import logging
import jwt
from transfers import transfers_bp
from waivers import waivers_bp


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


SECRET_KEY = "Godiswatching"


@app.route("/teams/join", methods=["POST"])
def join_team():
    data = request.json

    # Extract required fields
    user_id = data.get("userId")
    league_id = data.get("leagueId")
    team_id = data.get("teamId")

    if not user_id or not league_id or not team_id:
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        user_id = ObjectId(user_id)
        league_id = ObjectId(league_id)
        team_id = ObjectId(team_id)
    except:
        return jsonify({"error": "Invalid ObjectId format"}), 400

    # Check if user already joined a team in this league
    existing_entry = db.userteams.find_one(
        {"userId": user_id, "leagueId": league_id})

    if existing_entry:
        return jsonify({"error": "User is already in a team for this league"}), 400

    # Insert new entry in user_teams collection
    new_entry = {
        "userId": user_id,
        "leagueId": league_id,
        "teamId": team_id
    }

    db.userteams.insert_one(new_entry)

    return jsonify({"message": "User successfully joined the team"}), 201


@app.route("/teams/my_team", methods=["GET"])
def get_my_team():
    user_id = request.args.get("userId")
    league_id = request.args.get("leagueId")

    if not user_id or not league_id:
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        user_id = ObjectId(user_id)  # Convert to ObjectId
        league_id = ObjectId(league_id)
    except:
        return jsonify({"error": "Invalid ObjectId format"}), 400

    # Find user's team in the given league
    user_team = db.userteams.find_one(
        {"userId": user_id, "leagueId": league_id})

    if not user_team:
        return jsonify({"error": "User is not part of any team in this league"}), 404

    team_id = user_team["teamId"]

    # Fetch team details
    team = db.teams.find_one({"_id": team_id}, {"teamName": 1})

    if not team:
        return jsonify({"error": "Team not found"}), 404

    # Fetch all users in this team
    team_members = db.userteams.find({"teamId": team_id}, {"userId": 1})

    # Get names of all team members
    member_ids = [member["userId"] for member in team_members]
    members = db.users.find({"_id": {"$in": member_ids}}, {"name": 1})

    member_names = [member["name"] for member in members]

    return jsonify({
        "teamId": str(team["_id"]),
        "teamName": team["teamName"],
        "members": member_names
    }), 200


@app.route('/google_auth', methods=['POST'])
def google_auth():
    # Parse JSON request data
    data = request.get_json()
    email = data.get('email')
    name = data.get('name')

    if not email or not name:
        return jsonify({"error": "Email and name are required!"}), 400

    collection = db["users"]
    existing_user = collection.find_one({"email": email})

    if existing_user:
        user_id = str(existing_user["_id"])
    else:
        user_data = {"email": email, "name": name}
        result = collection.insert_one(user_data)
        user_id = str(result.inserted_id)  # Get the generated user ID

    # Set token expiration to 3 months from the current time
    expiry_time = (datetime.utcnow() + timedelta(days=90)
                   ).strftime("%H:%M %m/%d/%Y")

    # Create JWT payload
    payload = {
        "userId": user_id,
        "email": email,
        "name": name,
        "expiryTimeStamp": expiry_time
    }

    # Generate JWT token
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    return jsonify({"token": token})


@app.route('/get_data', methods=['GET'])
def get_data_from_mongodb():
    # Get the collectionName and leagueId from query parameters
    collection_name = request.args.get('collectionName')
    league_id = request.args.get('leagueId')

    # Check if collectionName is provided
    if not collection_name:
        return jsonify({'error': 'collectionName is required'}), 400

    try:

        collection = db[collection_name]
        query = {}  # Default query

        # If leagueId is provided, filter by leagueId
        # If collectionName is "leagues", filter by _id
        if collection_name == "leagues" and league_id:
            query['_id'] = ObjectId(league_id)
        elif league_id:
            query['leagueId'] = ObjectId(league_id)
        print(query)
        # Retrieve data from MongoDB based on the query
        data_from_mongo = list(collection.find(query))
        print(data_from_mongo)
        serialized_data = json_util.dumps(data_from_mongo, default=str)

        return Response(serialized_data, mimetype="application/json")
    except Exception as e:
        logging.error(f"Error fetching data: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/delete_league', methods=['DELETE'])
def delete_league():
    try:
        # Get input data
        league_id = request.args.get("leagueId")

        if not league_id:
            return jsonify({'error': 'leagueId is required'}), 400

        league_object_id = ObjectId(league_id)

        # Step 1: Delete all league players with this leagueId
        db.leagueplayers.delete_many({"leagueId": league_object_id})
        db.teams.delete_many({"leagueId": league_object_id})

        # Step 2: Remove leagueId from joinedLeagues array in users collection
        db.users.update_many(
            {"joinedLeagues": str(league_id)},
            {"$pull": {"joinedLeagues": str(league_id)}}
        )

        # Step 3: Delete the league from leagues collection
        result = db.leagues.delete_one({"_id": league_object_id})

        if result.deleted_count == 0:
            return jsonify({'error': 'League not found'}), 404

        return jsonify({"message": "League deleted successfully"}), 200

    except Exception as e:
        logging.error(f"Error deleting league: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/add_team', methods=['POST'])
def add_team():
    try:
        data = request.json
        team_name = data.get("teamName")
        league_id = data.get("leagueId")
        league_type = data.get("leagueType")

        if not team_name or not league_id:
            return jsonify({'error': 'teamName and leagueId are required'}), 400

        team_data = {
            "teamName": team_name,
            "batCount": 0,
            "ballCount": 0,
            "fCount": 0,
            "totalCount": 0,
            "currentPurse": 7000,
            "maxBid": 6700,
            "arCount": 0,
            "leagueId": ObjectId(league_id)
        }

        # Add an array with 8 empty strings
        if league_type and league_type.upper() == "DRAFT":
            team_data["draftSequence"] = [""] * 8
        result = db.teams.insert_one(team_data)
        return jsonify({"message": "Team added successfully", "teamId": str(result.inserted_id)}), 201

    except Exception as e:
        logging.error(f"Error adding team: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/delete_team', methods=['DELETE'])
def delete_team():
    try:
        data = request.json
        team_id = data.get("teamId")

        if not team_id:
            return jsonify({'error': 'teamId is required'}), 400

        result = db.teams.delete_one({"_id": ObjectId(team_id)})

        if result.deleted_count == 0:
            return jsonify({'error': 'Team not found'}), 404

        return jsonify({"message": "Team deleted successfully"}), 200

    except Exception as e:
        logging.error(f"Error deleting team: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/edit_team', methods=['PUT'])
def edit_team():
    try:
        data = request.json
        team_id = data.get("teamId")
        new_team_name = data.get("teamName")

        if not team_id or not new_team_name:
            return jsonify({'error': 'teamId and teamName are required'}), 400

        result = db.teams.update_one(
            {"_id": ObjectId(team_id)},
            {"$set": {"teamName": new_team_name}}
        )

        if result.matched_count == 0:
            return jsonify({'error': 'Team not found'}), 404

        return jsonify({"message": "Team name updated successfully"}), 200

    except Exception as e:
        logging.error(f"Error editing team: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/create_league', methods=['POST'])
def create_league():
    try:
        # Get input data
        data = request.json
        useremail = data.get("useremail")
        league_name = data.get("league_name")
        league_type = data.get("league_type")

        if not useremail or not league_name or not league_type:
            return jsonify({'error': 'useremail, league_name, and league_type are required'}), 400

        # Step 1: Create new league entry
        league_data = {
            "league_name": league_name,
            "league_type": league_type,
            "admins": [useremail]
        }

        new_league = db.leagues.insert_one(league_data)
        league_id = new_league.inserted_id

        # Step 2: Copy players to leagueplayers collection
        players = db.players.find({})
        for player in players:
            player_copy = {
                "player_name": player["player_name"],
                "player_role": player["player_role"],
                "ipl_team_name": player["ipl_team_name"],
                "isOverseas": player["isOverseas"],
                "ipl_salary": player["ipl_salary"],
                "rank": player["rank"],
                "tier": player["tier"],
                "afc_base_salary": player["afc_base_salary"],
                "status": "unsold",
                "leagueId": league_id  # Reference the newly created league
            }
            db.leagueplayers.insert_one(player_copy)

        # Step 3: Add leagueId to user's joinedLeagues array
        db.users.update_one(
            {"email": useremail},
            # Ensures no duplicates
            {"$addToSet": {"joinedLeagues": str(league_id)}},
            upsert=True  # Creates user entry if not found
        )

        return jsonify({"message": "League created successfully", "leagueId": str(league_id)}), 201

    except Exception as e:
        logging.error(f"Error creating league: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/get_leagues_by_email', methods=['GET'])
def get_leagues_by_email():
    try:
        email = request.args.get("email")

        if not email:
            return jsonify({'error': 'email is required'}), 400

        # Find the user by email
        user = db.users.find_one({"email": email}, {"joinedLeagues": 1})

        if not user or "joinedLeagues" not in user:
            return jsonify({"leagues": []}), 200

        league_ids = [ObjectId(lid) for lid in user["joinedLeagues"]]

        # Fetch league details from leagues collection
        leagues = list(db.leagues.find({"_id": {"$in": league_ids}}))

        # Convert ObjectId to string for JSON response
        for league in leagues:
            league["_id"] = str(league["_id"])

        return jsonify({"leagues": leagues}), 200

    except Exception as e:
        logging.error(f"Error fetching leagues: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/join_league', methods=['POST'])
def join_league():
    try:
        data = request.json
        email = data.get("email")
        league_id = data.get("leagueId")

        if not email or not league_id:
            return jsonify({'error': 'email and leagueId are required'}), 400

        league_object_id = ObjectId(league_id)

        # Find user by email
        user = db.users.find_one({"email": email})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Check if the user has already joined the league
        if "joinedLeagues" in user and league_id in user["joinedLeagues"]:
            return jsonify({'message': 'User already in league'}), 200

        # Add leagueId to the user's joinedLeagues array
        db.users.update_one(
            {"email": email},
            {"$push": {"joinedLeagues": league_id}}
        )

        return jsonify({"message": "User joined league successfully"}), 200

    except Exception as e:
        logging.error(f"Error joining league: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/getspecificplayer', methods=["GET"])
def get_a_player():
    name = request.args.get('player_name', '')
    name = urllib.parse.unquote(name)
    league_id = request.args.get('leagueId', '')

    player_query = {
        "player_name": {"$regex": name, "$options": 'i'},
        # status starts with 'unsold'
        "status": {"$regex": r"^unsold", "$options": "i"},
        "leagueId": ObjectId(league_id)
    }

    collection = db["leagueplayers"]
    player_data = collection.find_one(player_query)

    if player_data:
        return json.loads(json_util.dumps(player_data))
    else:
        # Return 404 status code
        return jsonify({"error": "Player not found"}), 404


@app.route('/getplayer', methods=["GET"])
def get_player():
    tiers = {1: [], 2: [], 3: [], 4: []}

    # Get the leagueID from the query parameter
    league_id = request.args.get('leagueId')
    if not league_id:
        return json.dumps({"message": "leagueID is required"}), 400

    collection = db['leagueplayers']

    cursor = collection.find({"leagueId": ObjectId(league_id)})
    for item in cursor:
        tier = item['tier']
        if tier in tiers and item['status'] == "unsold":
            tiers[tier].append(item)

    pick = None
    for tier in range(1, 5):
        if tiers[tier] and any(player['status'] == 'unsold' for player in tiers[tier]):
            pick = random.choice(
                [player for player in tiers[tier] if player['status'] == 'unsold']
            )
            break

    if pick is not None:
        return json.loads(json_util.dumps(pick))
    else:
        return json.dumps({"message": "All players are processed"}), 404


def handle_special_league_case(updated_data, player_data):
    if not player_data:
        return

    target_league_id = ObjectId('67d4dd408786c3e1b4ee172a')
    if player_data.get('leagueId') == target_league_id and updated_data['status'] == "sold":
        updated_data["todayPoints"] = 0
        updated_data["transferredPoints"] = player_data.get('points', 0)


@app.route('/updateplayer/<_id>', methods=['PUT'])
def update_player(_id):
    updated_data = request.get_json()
    filter = {"_id": ObjectId(str(_id))}

    collections = db["leagueplayers"]
    player_data = collections.find_one(filter)
    handle_special_league_case(updated_data, player_data)

    # Exclude _id from update_data to avoid updating it
    updated_data.pop('_id', None)
    result = collections.update_one(filter, {"$set": updated_data})

    if updated_data['status'] == "sold":
        ownercollection = db["teams"]
        update_owner_data(updated_data, ownercollection,
                          player_data.get('leagueId'))

    return json_util.dumps(result.raw_result)


def update_owner_data(updated_data, ownercollection, leagueId):
    owner_team = updated_data['ownerTeam']
    myquery = {"teamName": owner_team, "leagueId": leagueId}
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

    role = updated_data["player_role"].upper()
    if role == "BATTER":
        owner_items["batCount"] += 1
    elif role == "BOWLER":
        owner_items["ballCount"] += 1
    elif role == "ALL_ROUNDER":
        owner_items["arCount"] += 1

    else:
        print("Role not found")

    if updated_data["isOverseas"]:
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
            "status": "unsold"
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


@app.route('/drop_player/<_id>', methods=['PUT'])
def drop_player(_id):
    # Filter to identify the player to delete
    id_filter = {"_id": ObjectId(_id)}

    # Get the collectionName from the query parameter
    collection_name = request.args.get(
        'collectionName', 'efl_playersCentral_test')

    # Get player information from playerCentral
    player_collection = db[collection_name]
    player_data = player_collection.find_one(id_filter)

    # Retrieve necessary fields from player data
    amount = player_data.get("boughtFor", 0)
    owner_team = player_data.get("ownerTeam", "")
    player_name = player_data.get("player_name", "")
    points = player_data.get("points", 0)
    transfer_date = datetime.now().strftime("%d %B, %Y")

    # Update player data to reset boughtFor and ownerName
    update_data = {
        "$set": {
            "boughtFor": 0,
            "ownerTeam": "",
            "status": "unsold-dropped",
            "points": 0,
        }
    }

    # Update player in the collection
    result = player_collection.update_one(id_filter, update_data)

    # Query to find owner's data
    owner_query = {"teamName": owner_team}
    ownercollection_name = request.args.get(
        'ownerCollectionName', 'efl_ownerTeams_test')
    ownercollection = db[ownercollection_name]
    owner = ownercollection.find_one(owner_query)

    # Add transfer history to owner
    transfer_history_entry = {
        "player_name": player_name,
        "points": points,
        "transfer_date": transfer_date,
        "boughtFor": amount
    }
    if "transferHistory" not in owner:
        owner["transferHistory"] = [transfer_history_entry]
    else:
        owner["transferHistory"].append(transfer_history_entry)

    # Adjust owner's current purse and total count
    owner["currentPurse"] += int(amount)
    owner["totalCount"] -= 1

    # Adjust max bid based on total count
    owner["maxBid"] = owner["currentPurse"] - \
        (20 * (15 - owner["totalCount"]-1))

    # Adjust specific count based on player's role
    role = player_data.get("player_role", "")
    if role == "Batter":
        owner["batCount"] -= 1
    elif role == "Bowler":
        owner["ballCount"] -= 1
    elif role == "All-Rounder":
        owner["arCount"] -= 1
    elif role == "WK Keeper - Batter":
        owner["batCount"] -= 1
        owner["wkCount"] -= 1

    # Adjust foreign player count if necessary
    if player_data.get("country", "") != "India":
        owner["fCount"] -= 1

    # Update owner data in the collection
    ownercollection.update_one({"_id": owner["_id"]}, {"$set": owner})

    # Return the result of updating the player
    return json_util.dumps(result.raw_result)


def update_timestamp_points(attribute_name):
    pst_tz = timezone(timedelta(hours=-7))
    # Get the current date and time
    now = datetime.now(pst_tz)

    # Format the timestamp string
    timestamp_str = now.strftime("%B %d, %Y at %I:%M%p").replace(" 0", " ")
    globalCollection = db['global_data']
    if attribute_name == "rankingsUpdatedAt":
        responses = get_valid_responses()
        matchid = responses[-1]["match"]["objectId"]
        globalCollection.update_one(
            {},
            {"$set": {
                attribute_name: timestamp_str,
                "last-match-id": matchid
            }}
        )

    else:
        globalCollection.update_one(
            {}, {"$set": {attribute_name: timestamp_str}})


@app.route('/update_timestamp', methods=['POST'])
def update_timestamp():
    update_timestamp_points('rankingsUpdatedAt')
    return json_util.dumps("Success")


@app.route('/eod_update_rank', methods=['POST'])
def eod_update_rank():
    ownerCollectionName = request.args.get(
        'ownerCollectionName', 'efl_ownerTeams_test')
    ownerCollection = db[ownerCollectionName]
    documents = ownerCollection.find().sort("totalPoints", DESCENDING)

    # Initialize rank counter
    rank = 1

    # Update documents with rank and standings
    for document in documents:
        document_id = document["_id"]
        standings = document.get("standings", [])
        standings.append(rank)

        # Update the document with rank and standings
        ownerCollection.update_one({"_id": document_id}, {
                                   "$set": {"rank": rank, "standings": standings}})

        rank += 1

    return "OK", 200


@app.route('/eod_update_score', methods=['POST'])
def eod_update_score():
    collection_name = request.args.get(
        'collectionName', 'efl_playersCentral_test')
    collection = db[collection_name]
    ownerCollectionName = request.args.get(
        'ownerCollectionName', 'efl_ownerTeams_test')
    ownerCollection = db[ownerCollectionName]
    players = collection.find({"status": "sold"})
    owners = ownerCollection.find()
    bulk_updates = []
    for player in players:
        today_points = player.get('todayPoints', {}).get('total_points', 0)
        total_points = player.get('points', 0)
        total_points += today_points
        bulk_updates.append(
            UpdateOne(
                {"_id": player["_id"]},
                {"$set": {"points": total_points}}
            )
        )
    # Perform bulk update
    if bulk_updates:
        collection.bulk_write(bulk_updates)

    bulk_updates = []
    for owner in owners:
        today_points = owner.get('todayPoints', 0)
        total_points = owner.get('totalPoints', 0)
        total_points += today_points
        bulk_updates.append(
            UpdateOne(
                {"_id": owner["_id"]},
                {"$set": {"totalPoints": total_points}}
            )
        )

    # Perform bulk update
    if bulk_updates:
        ownerCollection.bulk_write(bulk_updates)
    return 'OK', 200


def get_global_data(attribute_name):
    global_collection = db['global_data']
    document = global_collection.find_one({})
    return document[attribute_name]


def is_valid(id):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    url = f"https://hs-consumer-api.espncricinfo.com/v1/pages/match/details?lang=en&seriesId=1411166&matchId={id}&latest=true"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        stage = data["match"]["stage"]
        if stage.upper() == "SCHEDULED" or not data['scorecard']:
            return None
        return data
    else:
        return None


def get_valid_responses():
    matchid = get_global_data('last-match-id')
    matchid1 = matchid+1
    matchid2 = matchid+2
    matchid3 = matchid+3
    responses = []
    response = is_valid(matchid1)
    if response:
        responses.append(response)
    response = is_valid(matchid2)
    if response:
        responses.append(response)
    response = is_valid(matchid3)
    if response:
        responses.append(response)
    return responses


def reset_player_points(collection):
    """Reset today's points for all players to 0."""
    bulk_updates = []
    players = collection.find({"status": "sold"})
    for player in players:
        bulk_updates.append(
            UpdateOne(
                {"_id": player["_id"]},
                {"$set": {
                    "todayPoints.batting_points": 0,
                    "todayPoints.bowling_points": 0,
                    "todayPoints.fielding_points": 0,
                    "todayPoints.total_points": 0
                }}
            )
        )
    if bulk_updates:
        collection.bulk_write(bulk_updates)


def process_matches(responses, collection, owner_collection):
    """Process multiple matches."""
    for response in responses:
        process_match(response, collection, owner_collection)


def update_player_points(collection, player_points):
    """Update player points in the collection."""
    bulk_updates = []
    for player_data in player_points:
        player_name = player_data['playername']
        existing_player = collection.find_one({"player_name": player_name})
        if not existing_player:
            print(player_name)
        bulk_updates.append(
            UpdateOne(
                {"player_name": player_name},
                {"$set": {
                    "todayPoints.batting_points": player_data['batting points'],
                    "todayPoints.bowling_points": player_data['bowling points'],
                    "todayPoints.fielding_points": player_data['fielding points'],
                    "todayPoints.total_points": player_data['total_points']
                }}
            )
        )
    if bulk_updates:
        collection.bulk_write(bulk_updates)


def process_match(response, collection, owner_collection):
    """Process the match data."""
    scorecard = extract_scorecard(response)
    player_points = calculate_points_for_players(scorecard)
    update_player_points(collection, player_points)
    update_owner_points(collection, owner_collection)


@app.route('/update_score_new', methods=['POST'])
def update_score_new():
    responses = get_valid_responses()
    collection_name = request.args.get(
        'collectionName', 'eflDraft_playersCentral')
    owner_collection_name = request.args.get(
        'ownerCollectionName', 'eflDraft_ownerTeams')
    collection = db[collection_name]
    owner_collection = db[owner_collection_name]
    # Reset player points before processing matches
    reset_player_points(collection)
    process_matches(responses, collection, owner_collection)
    update_timestamp_points("pointsUpdatedAt")
    return 'OK', 200

# Endpoint to update fantasy league scores


@app.route('/update_score', methods=['POST'])
def update_score():
    matchid = get_global_data('last-match-id')
    #matchids = get_valid_ids(matchid)
    url = "https://hs-consumer-api.espncricinfo.com/v1/pages/match/details?lang=en&seriesId=1410320&matchId=1422125&latest=true"
    scorecard = extract_scorecard(url)
    # print(scorecard)
    player_points = calculate_points_for_players(scorecard)
    collection_name = request.args.get(
        'collectionName', 'efl_playersCentral_test')

    collection = db[collection_name]

    # reset today's points to 0
    bulk_updates = []
    players = collection.find({"status": "sold"})
    for player in players:
        bulk_updates.append(
            UpdateOne(
                {"_id": player["_id"]},
                {"$set": {
                    "todayPoints.batting_points": 0,
                    "todayPoints.bowling_points": 0,
                    "todayPoints.fielding_points": 0,
                    "todayPoints.total_points": 0
                }}
            )
        )
    if bulk_updates:
        collection.bulk_write(bulk_updates)

    # Update each document in bulk
    bulk_updates = []

    for player_data in player_points:
        player_name = player_data['playername']
        existing_player = collection.find_one({"player_name": player_name})
        if not existing_player:
            print(player_name)
        bulk_updates.append(
            UpdateOne(
                {"player_name": player_name},
                {"$set": {
                    "todayPoints.batting_points": player_data['batting points'],
                    "todayPoints.bowling_points": player_data['bowling points'],
                    "todayPoints.fielding_points": player_data['fielding points'],
                    "todayPoints.total_points": player_data['total_points']
                }}
            )
        )
    if bulk_updates:
        collection.bulk_write(bulk_updates)
    ownerCollection = request.args.get(
        'ownerCollectionName', 'efl_ownerTeams_test')

    ownerCollection = db[ownerCollection]
    update_owner_points(collection, ownerCollection)
    return 'OK', 200


def update_owner_points(collection, ownerCollection):
    owners_points = {}
    players = collection.find({"status": "sold"})
    for player in players:
        owner_name = player.get('ownerTeam')
        today_points = player.get('todayPoints', {}).get('total_points', 0)
        owners_points[owner_name] = owners_points.get(
            owner_name, 0) + today_points

    # Step 2: Determine rank of each owner based on todayPoints

    bulk_updates = []
    owners = ownerCollection.find()
    for owner in owners:
        ownerName = owner.get('teamName')
        if ownerName in owners_points:
            bulk_updates.append(
                UpdateOne(
                    {"teamName": ownerName},
                    {"$set": {"todayPoints": owners_points[ownerName]}}
                )
            )
        else:
            bulk_updates.append(
                UpdateOne(
                    {"teamName": ownerName},
                    {"$set": {"todayPoints": 0}}
                )
            )

    # Execute bulk update operations
    if bulk_updates:
        ownerCollection.bulk_write(bulk_updates)

    print("Owners data updated successfully.")


def calculate_batting_points(batting_stats):
    runs = batting_stats['runs']
    fours = batting_stats['fours']
    sixes = batting_stats['sixes']
    strike_rate = batting_stats['sr']
    isOut = batting_stats['isOut']
    balls = batting_stats['balls']

    points = runs + fours + (2 * sixes)

    if runs >= 100:
        points += 16
    elif runs >= 50:
        points += 8
    elif runs >= 30:
        points += 4

   # Perform the calculation only if balls >= 10
    if balls >= 10:
        if strike_rate > 170:
            points += 6
        elif 150.01 <= strike_rate <= 170:
            points += 4
        elif 130 <= strike_rate < 150:
            points += 2
        elif 50 <= strike_rate <= 59.99:
            points -= 4
        elif strike_rate < 50:
            points -= 6

    if isOut and runs == 0:
        points -= 2

    return points


def calculate_bowling_points(bowling_stats):
    wickets = bowling_stats['wickets']
    # Assuming maiden_overs is provided
    maiden_overs = bowling_stats.get('maidens', 0)
    economy = bowling_stats.get('economy', 7.1)  # Assuming economy is provided
    lbw_bowled_count = bowling_stats.get('lbwbowledcount', 0)
    overs_bowled = bowling_stats.get('overs', 0)

    points = 25 * wickets

    points += 8 * lbw_bowled_count

    if wickets >= 5:
        points += 16
    elif wickets == 4:
        points += 8
    elif wickets == 3:
        points += 4

    points += 12 * maiden_overs

    if overs_bowled >= 2:
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
    batting_points = calculate_batting_points(
        player['batting']) if 'batting' in player else 0
    bowling_points = calculate_bowling_points(
        player['bowling']) if 'bowling' in player else 0
    fielding_points = calculate_fielding_points(
        player['fielding']) if 'fielding' in player else 0

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


def get_count_of_lbw_and_bowled(bowler):
    count = 0
    for wicket in bowler['inningWickets']:
        if wicket['dismissalType'] in [2, 3]:
            count += 1
    return count


def extract_scorecard(data):
    player_stats = []

    for inning in data.get("scorecard", {}).get("innings", []):
        bat_stats = []
        bowl_stats = []
        field_stats = {}

        for batsman in inning.get("inningBatsmen", []):
            if batsman.get("battedType") == "yes":
                bat_stats.append({
                    "player_name": batsman["player"]["longName"],
                    "batting": {
                        "runs": batsman["runs"],
                        "balls": batsman["balls"],
                        "fours": batsman["fours"],
                        "sixes": batsman["sixes"],
                        "sr": batsman["strikerate"],
                        "isOut": batsman["isOut"]
                    }
                })

        for bowler in inning.get("inningBowlers", []):
            bowl_stats.append({
                "player_name": bowler["player"]["longName"],
                "bowling": {
                    "wickets": bowler["wickets"],
                    "maidens": bowler["maidens"],
                    "economy": bowler["economy"],
                    "lbwbowledcount": get_count_of_lbw_and_bowled(bowler),
                    "overs": bowler["overs"]
                }
            })

        for wicket in inning.get("inningWickets", []):
            dismissal_type = wicket.get("dismissalType")
            fielders = wicket.get("dismissalFielders", [])
            for fielder in fielders:
                player_info = fielder.get("player")
                if player_info and player_info != "null":
                    player_name = player_info["longName"]
                    field_stats[player_name] = field_stats.get(player_name, {
                                                               "player_name": player_name, "fielding": {"catches": 0, "runouts": 0, "stumpings": 0}})
                    if dismissal_type == 1:
                        field_stats[player_name]["fielding"]["catches"] += 1
                    elif dismissal_type == 4:
                        field_stats[player_name]["fielding"]["runouts"] += 1
                    elif dismissal_type == 5:
                        field_stats[player_name]["fielding"]["stumpings"] += 1

        player_stats.extend(bat_stats + bowl_stats +
                            list(field_stats.values()))

    merged_data = {}
    for player_stat in player_stats:
        player_name = player_stat['player_name']
        if player_name not in merged_data:
            merged_data[player_name] = {'player_name': player_name}
        merged_data[player_name].update(player_stat)

    return list(merged_data.values())


def update_player_scores(collection):
    players = collection.find({"status": "sold"})
    bulk_updates = []

    for player in players:
        today_points = player.get('todayPoints', {}).get('total_points', 0)
        total_points = player.get('points', 0)
        total_points += today_points
        bulk_updates.append(
            UpdateOne(
                {"_id": player["_id"]},
                {"$set": {"points": total_points}}
            )
        )

    if bulk_updates:
        collection.bulk_write(bulk_updates)


def update_owner_scores(owner_collection):
    owners = owner_collection.find()
    bulk_updates = []

    for owner in owners:
        today_points = owner.get('todayPoints', 0)
        total_points = owner.get('totalPoints', 0)
        total_points += today_points
        bulk_updates.append(
            UpdateOne(
                {"_id": owner["_id"]},
                {"$set": {"totalPoints": total_points}}
            )
        )

    if bulk_updates:
        owner_collection.bulk_write(bulk_updates)


def update_ranks(owner_collection):
    documents = owner_collection.find().sort("totalPoints", DESCENDING)
    rank = 1

    for document in documents:
        document_id = document["_id"]
        standings = document.get("standings", [])
        standings.append(rank)

        owner_collection.update_one(
            {"_id": document_id},
            {"$set": {"rank": rank, "standings": standings}}
        )

        rank += 1


def get_most_valuable_players(api_url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        player_map = {}

        for result in data['content']['smartStats']['results']:
            # Extracting player name and points
            player_name = result['player']['longName']
            points = result['totalImpact']

            # Convert player name to the required format (S Narine)
            split_name = player_name.split()
            if len(split_name) > 1:
                first_name = split_name[0][0]
                last_name = split_name[-1]
                formatted_name = f"{first_name} {last_name}"
            else:
                formatted_name = player_name

            # Add player name and points to the map
            player_map[formatted_name] = points

        return player_map

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None


def update_mongo_collection_family(player_points_map):

    collection = db["family_playerPoints"]

    bulk_operations = []

    # Iterate through all documents in the collection
    for team_doc in collection.find():
        team_name = team_doc["team_name"]
        players = team_doc["players"]

        # Initialize team total points
        team_total_points = 0

        # Iterate through players in the team
        for player in players:
            player_name = player["player_name"]

            # Look up points for the player in the player_points_map
            if player_name in player_points_map:
                points = player_points_map[player_name]
                team_total_points += points

                # Update player's points in the collection
                bulk_operations.append(
                    UpdateOne(
                        {"team_name": team_name, "players.player_name": player_name},
                        {"$set": {"players.$.points": points}}
                    )
                )
            else:
                print(f"No points found for player '{player_name}'.")

        # Update total points for the team in the collection
        bulk_operations.append(
            UpdateOne(
                {"team_name": team_name},
                {"$set": {"total": team_total_points}}
            )
        )

    # Execute bulk operations
    result = collection.bulk_write(bulk_operations)

    # Print result if needed
    print(result.bulk_api_result)


def update_family_league():
    api_url = "https://hs-consumer-api.espncricinfo.com/v1/pages/series/most-valuable-players?lang=en&seriesId=1410320"
    player_points_map = get_most_valuable_players(api_url)
    update_mongo_collection_family(player_points_map)


@app.route('/eod_update', methods=['POST'])
def eod_update():
    collection_name = request.args.get(
        'collectionName', 'eflDraft_playersCentral')
    owner_collection_name = request.args.get(
        'ownerCollectionName', 'eflDraft_ownerTeams')

    collection = db[collection_name]
    owner_collection = db[owner_collection_name]

    update_player_scores(collection)
    update_owner_scores(owner_collection)
    update_ranks(owner_collection)
    update_timestamp_points('rankingsUpdatedAt')
    return 'OK', 200


app.register_blueprint(draftapi_bp)
app.register_blueprint(liveupdates_bp)
app.register_blueprint(transfers_bp, name="transfers_unique")
app.register_blueprint(waivers_bp)

if __name__ == '__main__':
    # Run the Flask app on http://127.0.0.1:5000/
    '''
    url = "https://hs-consumer-api.espncricinfo.com/v1/pages/match/scorecard?lang=en&seriesId=1434088&matchId=1434104&latest=true"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
    scorecard = extract_scorecard(data)
    # print(scorecard)
    print(calculate_points_for_players(scorecard))
    '''

    app.run()
