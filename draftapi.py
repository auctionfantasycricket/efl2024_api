from flask import Blueprint, request
from config import db, app
from bson import ObjectId, json_util
from datetime import datetime, timedelta
from collections import deque
import base64


draftapi_bp = Blueprint('draftapi', __name__)


def update_owner_data(updated_data, ownercollection, player_data, league_id):
    owner_team = updated_data['ownerTeam']
    myquery = {"teamName": owner_team, "leagueId": ObjectId(str(league_id))}
    owners_data = ownercollection.find(myquery)

    for owner_items in owners_data:
        owner_items = update_owner_items(owner_items, player_data)
        filter_owner = {"_id": ObjectId(str(owner_items["_id"]))}
        ownercollection.update_one(filter_owner, {"$set": owner_items})


def update_owner_items(owner_items, player_data):

    owner_items["totalCount"] += 1

    role = player_data["player_role"].upper()
    if role == "BATTER":
        owner_items["batCount"] += 1
    elif role == "BOWLER":
        owner_items["ballCount"] += 1
    elif role == "ALL_ROUNDER":
        owner_items["arCount"] += 1
    else:
        print("Role not found")

    if player_data["isOverseas"]:
        owner_items["fCount"] += 1

    # Iterate through draftSequence to find the first empty string and update it
    if "draftSequence" not in owner_items:
        owner_items["draftSequence"] = []  # Initialize if missing

    for i, name in enumerate(owner_items["draftSequence"]):
        if not name.strip():  # Check if the string is empty after stripping whitespace
            owner_items["draftSequence"][i] = player_data["player_name"]
            break  # Stop iterating after updating the first empty string

    return owner_items


@draftapi_bp.route('/getrandomdraftplayer', methods=["GET"])
def get_random_player():
    collection_name = request.args.get(
        'collectionName', 'eflDraft_playersCentral')
    collection = db[collection_name]

    # Using aggregation to get a random unsold player
    pipeline = [
        {"$match": {"status": "unsold"}},
        {"$sample": {"size": 1}}
    ]

    player_data = list(collection.aggregate(pipeline))

    if player_data:
        return json_util.dumps(player_data[0])
    else:
        return json_util.dumps("no unsold player found")


def fetch_team_owners_by_email(email, owner_collection_name):
    team_owners = db[owner_collection_name]
    return list(team_owners.find({'emails': email}))


@draftapi_bp.route('/getTeamById/<teamId>', methods=['GET'])
def get_team_by_id(teamId):
    try:
        # Look up the team by teamId
        team = db.teams.find_one({'_id': ObjectId(teamId)}, {
                                 'teamName': 1, 'currentWaiver': 1})

        if not team:
            return json_util.dumps({'error': 'Team not found'}), 404

        # Return teamName and currentWaiver
        response = {
            'teamName': team.get('teamName'),
            'currentWaiver': team.get('currentWaiver')
        }
        return json_util.dumps(response), 200

    except Exception as e:
        return json_util.dumps({'error': str(e)}), 500


def get_team_owner_response(team_owners_found):
    if not team_owners_found:
        return {'error': 'No team owners found for this email'}, 404
    elif len(team_owners_found) > 1:
        return {'error': 'Multiple team owners found for this email'}, 500
    else:
        return {
            'teamName': team_owners_found[0]['teamName'],
            'currentWaiver': team_owners_found[0]['currentWaiver']
        }, 200


def get_team_owner_by_email(email):
    try:
        owner_collection_name = request.args.get(
            'ownerCollectionName', 'eflDraft_ownerTeams')
        team_owners_found = fetch_team_owners_by_email(
            email, owner_collection_name)
        response_data, status_code = get_team_owner_response(team_owners_found)
        response = json_util.dumps(response_data)
        return response, status_code
    except Exception as e:
        response = json_util.dumps({'error': str(e)})
        return response, 500

# Define the route


@draftapi_bp.route('/getTeamOwnerByEmail/<email>', methods=['GET'])
def get_team_owner(email):
    return get_team_owner_by_email(email)


def validate_waiver_data(current_waiver):
    if len(current_waiver.get('in', [])) != 4:
        return False, "The 'in' array must contain exactly 4 elements."
    if len(current_waiver.get('out', [])) != 2:
        return False, "The 'out' array must contain exactly 2 elements."
    return True, ""


def decrypt_arr(arr):
    outArr = []
    # for el in arr:
    # outArr.append(decrypt_aes(el))
    return outArr


def de_arr(arr):
    output = []
    for a in arr:
        output.append(base64.b64decode(a).decode('utf-8'))
    return output


def get_teams_and_sort():
    # 1 Get Teams
    owner_collection_name = request.args.get(
        'ownerCollectionName', 'eflDraft_ownerTeams')
    ownercollection = db[owner_collection_name]
    allDocs = ownercollection.find().sort('rank', -1)
    docs_dict = {}
    docs_list = []

    for doc in allDocs:
        teamName = doc["teamName"]
        docs_dict[teamName] = {'in': [], 'out': []}
        decodedarr = de_arr(doc["currentWaiver"]["in"])
        docs_dict[teamName]['in'].extend(decodedarr)
        decodedarr = de_arr(doc["currentWaiver"]["out"])
        # decrypt_arr(doc["currentWaivers"]["in"]))
        docs_dict[teamName]['out'].extend(decodedarr)
        docs_dict[teamName]['batCount'] = doc["batCount"]
        docs_dict[teamName]['arCount'] = doc["arCount"]
        docs_dict[teamName]['wkCount'] = doc["wkCount"]
        docs_dict[teamName]['fCount'] = doc["fCount"]
        docs_dict[teamName]['ballCount'] = doc["ballCount"]
        # decrypt_arr(doc["currentWaivers"]["out"]))
        docs_list.append(teamName)

    return docs_dict, docs_list

# Function to generate waiver orders


def generate_waiver_orders(docs, num_orders):
    waiver_orders = []
    d = deque(docs)
    for _ in range(num_orders):
        waiver_orders.append(list(d))
        d.rotate(-1)  # Rotate the deque to the left
    return waiver_orders


def getRoleAndCountry(player):
    player_col_name = 'eflDraft_playersCentral'
    playerCollection = db[player_col_name]
    player = playerCollection.find_one({'player_name': player})

# Check if player is found and return the player_role and country
    if player:
        player_role = player.get('player_role')
        country = player.get('country')
        return player_role, country
    else:
        return None, None


def swap_possible(teamName, teamdict, inPlayer, outPlayer):
    #inPlayer = 'Virat Kohli'
    inRole, inCountry = getRoleAndCountry(inPlayer)
    #outPlayer = 'Rohit Sharma'
    outRole, outCountry = getRoleAndCountry(outPlayer)
    if not inRole or not inCountry or not outRole or not outCountry:
        return False

    tempBatCount, tempBallCount, tempARCount, tempWKCount, tempFCount = teamdict[teamName]['batCount'], teamdict[
        teamName]['ballCount'], teamdict[teamName]['arCount'], teamdict[teamName]['wkCount'], teamdict[teamName]['fCount']

    if inRole == "batter":
        tempBatCount += 1
    elif inRole == "bowler":
        tempBallCount += 1
    elif inRole == "allrounder":
        tempARCount += 1
    elif inRole == "wicketkeeper":
        tempBatCount += 1
        tempWKCount += 1

    associate_nations = ["Canada", "Namibia", "Nepal", "Netherlands", "Oman",
                         "Papua-new-guinea", "Scotland", "Uganda", "United-states-of-america", "Ireland"]

    if inCountry in associate_nations:
        tempFCount += 1
    if outCountry in associate_nations:
        tempFCount -= 1

    if outRole == "batter":
        tempBatCount -= 1
    elif outRole == "bowler":
        tempBallCount -= 1
    elif outRole == "allrounder":
        tempARCount -= 1
    elif outRole == "wicketkeeper":
        tempBatCount -= 1
        tempWKCount -= 1

    if tempBatCount >= 4 and tempBallCount >= 4 and tempARCount >= 1 and tempWKCount >= 1:
        return True
    else:
        return False


def check_criteria(teamName, teamdict, playerName, outArr):
    outRet = ''
    success = False
    for i, o in enumerate(outArr):
        if o == 'X':
            continue
        if o == '':
            success = False
            break
        if swap_possible(teamName, teamdict, playerName, o):
            outRet = o
            outArr[i] = 'X'
            success = True
            break
        else:
            outRet = o
            success = False
            break

    return success, outRet, outArr


def decode_and_process(orders, docs_dict):
    results = []
    playersTaken = set()
    teamPlayersIn = {}
    teamPlayersOut = {}
    for team in orders[0]:
        teamPlayersIn[team] = []
        teamPlayersOut[team] = []
    print(docs_dict)
    bulk_add_input = []
    bulk_out_input = []
    animation_input = {}
    print(end='\n')
    print(docs_dict, end='\n')
    for i in range(4):
        obj = {'pref': i+1, 'picks': [], 'result': [], 'reason': []}
        for teamToProcess in orders[i]:
            # in, out = decrypt_waivers(docs_dict[teamtoProcess])

            playerToProcess = docs_dict[teamToProcess]['in'][i]
            obj['picks'].append(teamToProcess + ' -> ' + playerToProcess)
            if len(teamPlayersIn[teamToProcess]) == 2:
                obj['result'].append('Fail')
                obj['reason'].append(teamToProcess + ' already picked up 2')
                animation_input[(teamToProcess, playerToProcess)] = False
                continue
            if playerToProcess == '':
                obj['result'].append('Fail')
                obj['reason'].append('empty player')
                animation_input[(teamToProcess, playerToProcess)] = False
                continue
            if playerToProcess in playersTaken:
                obj['result'].append('Fail')
                obj['reason'].append(playerToProcess + ' already taken')
                animation_input[(teamToProcess, playerToProcess)] = False
                continue

            satisfied, outPlayer, docs_dict[teamToProcess]['out'] = check_criteria(
                teamToProcess, docs_dict, playerToProcess, docs_dict[teamToProcess]['out'])
            if not satisfied:
                obj['result'].append('Fail')
                obj['reason'].append('getting ' + playerToProcess + ' and dropping ' +
                                     outPlayer + ' breaks team restriction condition')
                animation_input[(teamToProcess, playerToProcess)] = False
            else:
                obj['result'].append('Successful')
                obj['reason'].append(
                    teamToProcess+' gets ' + playerToProcess + ' and drops ' + outPlayer)
                teamPlayersIn[teamToProcess].append(playerToProcess)
                teamPlayersOut[teamToProcess].append(outPlayer)
                playersTaken.add(playerToProcess)
                input_obj = {'teamName': teamToProcess,
                             'playerName': playerToProcess}
                bulk_add_input.append(input_obj)
                bulk_out_input.append(outPlayer)
                animation_input[(teamToProcess, playerToProcess)] = True

        results.append(obj)
    print(end='\n')
    print(bulk_add_input, end='\n')
    print(end='\n')
    print(bulk_out_input, end='\n')
    print(end='\n')
    print(results, end='\n')
    print(end='\n')
    print(orders, end='\n')
    print(end='\n')
    print(animation_input, end='\n')

    return results


@draftapi_bp.route('/drop_draft_player/<input_player>', methods=['PUT'])
def drop_draft_player(input_player):
    # Filter to identify the player to delete
    id_filter = {"player_name": input_player}

    # Get the collectionName from the query parameter
    collection_name = request.args.get(
        'collectionName', 'eflDraft_playersCentral')

    # Get player information from playerCentral
    player_collection = db[collection_name]
    player_data = player_collection.find_one(id_filter)

    # Retrieve necessary fields from player data

    owner_team = player_data.get("ownerTeam", "")
    player_name = player_data.get("player_name", "")
    points = player_data.get("points", 0)
    transfer_date = datetime.now().strftime("%d %B, %Y")

    # Update player data to reset boughtFor and ownerName
    update_data = {
        "$set": {

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
        'ownerCollectionName', 'eflDraft_ownerTeams')
    ownercollection = db[ownercollection_name]
    owner = ownercollection.find_one(owner_query)

    # Add transfer history to owner
    transfer_history_entry = {
        "player_name": player_name,
        "points": points,
        "transfer_date": transfer_date,

    }
    if "transferHistory" not in owner:
        owner["transferHistory"] = [transfer_history_entry]
    else:
        owner["transferHistory"].append(transfer_history_entry)

    owner["totalCount"] -= 1

    # Adjust specific count based on player's role
    role = player_data.get("player_role", "")
    if role == "batter":
        owner["batCount"] -= 1
    elif role == "bowler":
        owner["ballCount"] -= 1
    elif role == "allrounder":
        owner["arCount"] -= 1
    elif role == "wicketkeeper":
        owner["batCount"] -= 1
        owner["wkCount"] -= 1
    else:
        print("Role not found")

    # Adjust foreign player count if necessary

    associate_nations = ["Canada", "Namibia", "Nepal", "Netherlands", "Oman",
                         "Papua-new-guinea", "Scotland", "Uganda", "United-states-of-america", "Ireland"]

    if player_data["country"] in associate_nations:
        owner["fCount"] -= 1

    # Update owner data in the collection
    ownercollection.update_one({"_id": owner["_id"]}, {"$set": owner})

    # Return the result of updating the player
    return json_util.dumps(result.raw_result)


@draftapi_bp.route('/processWaivers', methods=['POST'])
def process_waivers():
    # 1 Get and Sort
    docs_dict, docs_list = get_teams_and_sort()
    # 2 create waiver orders
    waiver_orders = generate_waiver_orders(docs_list, 4)

    # 3 process
    results = decode_and_process(waiver_orders, docs_dict)
    #encoded_string = "QWFyb24gSm9obnNvbg=="

    # player = base64.b64decode(encoded_string).decode(
    #    'utf-8')
    # prepare results
    # reset waivers
    return docs_dict, 200


def is_before_deadline(deadline_str):
    # Remove the timezone part and parse the time
    datetime_part = deadline_str.split(' (')[0]  # "April 6, 2025 at 1:00PM"
    deadline_naive = datetime.strptime(datetime_part, "%B %d, %Y at %I:%M%p")

    # PST is UTC-8, but in April, Daylight Saving Time (PDT = UTC-7) applies
    # So we manually adjust for PDT (UTC-7)
    deadline_utc = deadline_naive + timedelta(hours=7)

    # Get current UTC time
    now_utc = datetime.utcnow()

    return now_utc < deadline_utc


def check_deadline_for_team(team_id, auction_league_id, draft_league_id):
    # Fetch the team
    team = db.teams.find_one({'_id': ObjectId(team_id)}, {'leagueId': 1})
    if not team or 'leagueId' not in team:
        return False, 'Team or leagueId not found'

    league_id = team['leagueId']

    # Determine deadline field based on league type
    if league_id == auction_league_id:
        deadline_field = 'nextAuctionDeadline'
    elif league_id == draft_league_id:
        deadline_field = 'nextDraftDeadline'
    else:
        return False, 'Unknown league type'

    # Fetch deadline from global_data
    global_data = db.global_data.find_one({}, {deadline_field: 1})
    if not global_data or deadline_field not in global_data:
        return False, f'{deadline_field} not set in global data'

    deadline_str = global_data[deadline_field]

    # Check the deadline
    if not is_before_deadline(deadline_str):
        return False, f'Cannot update waiver after the {deadline_field}'

    return True, None


@draftapi_bp.route('/updateCurrentWaiver/<userId>/<teamId>', methods=['PUT'])
def update_current_waiver_api(userId, teamId):
    try:
        auctionLeagueId = ObjectId('67d4dd408786c3e1b4ee172a')
        draftLeagueId = ObjectId('67da30b26a17f44a19c2241a')
        is_allowed, error_message = check_deadline_for_team(
            teamId, auctionLeagueId, draftLeagueId)
        if not is_allowed:
            return json_util.dumps({'error': error_message}), 400

        current_waiver = request.json.get('currentWaiver')

        # Validate currentWaiver data
        is_valid, validation_message = validate_waiver_data(current_waiver)
        if not is_valid:
            return json_util.dumps({'error': validation_message}), 400

        # Fetch user name from users collection
        user = db.users.find_one({'_id': ObjectId(userId)}, {'name': 1})
        if not user:
            return json_util.dumps({'error': 'User not found'}), 404
        user_name = user['name']

        # Get current UTC time and convert to PST (UTC-7)
        now_utc = datetime.utcnow()
        pst_offset = timedelta(hours=-7)
        now_pst = now_utc + pst_offset

        # Format the time
        current_waiver['lastUpdatedBy'] = user_name
        current_waiver['lastUpdatedTime'] = now_pst.strftime(
            '%dth %B at %I:%M:%S %p')

        # Update the team object in db.teams
        result = db.teams.update_one(
            {'_id': ObjectId(teamId)},
            {'$set': {'currentWaiver': current_waiver}}
        )

        # Add the current waiver to teamwaivers
        db.teamwaivers.update_one(
            {"teamId": ObjectId(teamId)},
            {"$push": {"waiverHistory": current_waiver}},
            upsert=True
        )

        if result.modified_count > 0:
            return json_util.dumps({'message': 'Current waiver updated successfully'}), 200
        else:
            return json_util.dumps({'error': 'Team not found or no update needed'}), 404

    except Exception as e:
        return json_util.dumps({'error': str(e)}), 500


@draftapi_bp.route('/draftplayer/<_id>', methods=['PUT'])
def draftplayer(_id):
    updated_data = request.get_json()
    print(_id)
    filter = {"_id": ObjectId(str(_id))}

    # Get collection names and leagueID from query parameters
    collection_name = request.args.get('collectionName', 'leagueplayers')
    owner_collection_name = request.args.get('ownerCollectionName', 'teams')
    league_id = updated_data.get('leagueID')

    playerCollection = db[collection_name]
    player_data = playerCollection.find_one(filter)

    if player_data is None:
        return json_util.dumps({"error": "Player not found"}), 404

    # Exclude _id from updated_data to avoid modifying it
    updated_data.pop('_id', None)

    today_points = {
        "batting_points": 0,
        "bowling_points": 0,
        "fielding_points": 0,
        "total_points": 0
    }

    # Add 'todayPoints' to updated_data
    updated_data["todayPoints"] = today_points
    result = playerCollection.update_one(filter, {"$set": updated_data})

    if updated_data.get('status', '').lower() == "sold":
        owner_collection = db[owner_collection_name]
        update_owner_data(updated_data, owner_collection,
                          player_data, league_id)

    return json_util.dumps(result.raw_result)


@draftapi_bp.route('/bulk-draftplayer', methods=['POST'])
def bulk_draftplayer():
    payloads = request.get_json()
    results = []

    with app.test_client() as client:
        for payload in payloads:

            collection_name = payload.get(
                "collectionName", "eflDraft_playersCentral")
            owner_collection_name = payload.get(
                "ownerCollectionName", "eflDraft_ownerTeams")
            player_name = payload.get('playerName', '')

            team_name = payload.get('teamName', '')
            collection = db[collection_name]

  # Find the document with the matching player name
            document = collection.find_one({"player_name": player_name})
            newpayload = {
                'ownerTeam': team_name, 'status': 'sold'
            }
    # Parse the ID from the _id field (assuming it's an ObjectId)
            player_id = str(document["_id"])  # Convert ObjectId to string
            # player_id =
            response = client.put(f'/draftplayer/{player_id}',
                                  json=newpayload,
                                  query_string={"collectionName": collection_name,
                                                "ownerCollectionName": owner_collection_name})
            print(response)
            # results.append(result)

    return True


@draftapi_bp.route('/bulk_drop_draft_player', methods=['POST'])
def bulk_drop_draft_player():
    """
    Bulk API to drop multiple draft players based on a list of player names.

    Returns:
        JSON response containing results (success/failure) for each player drop attempt.
    """

    payload = request.get_json()
    results = []

    if not payload or not isinstance(payload, list):
        # Handle invalid payload format
        return ({"error": "Invalid payload. Please provide a list of player names."}), 400

    for player_name in payload:
        # Call the drop_draft_player function for each player name
        response = drop_draft_player(player_name)
        results.append(response)

    return True


@draftapi_bp.route('/getWaiverHistory/<teamId>', methods=['GET'])
def get_waiver_history(teamId):
    try:
        # Query the teamwaivers collection for the waiver history of the given teamId
        waiver_history = db.teamwaivers.find_one(
            {"teamId": ObjectId(teamId)}, {"waiverHistory": 1})

        if not waiver_history or "waiverHistory" not in waiver_history:
            return json_util.dumps({"error": "No waiver history found for the given teamId"}), 404

        return json_util.dumps(waiver_history["waiverHistory"]), 200

    except Exception as e:
        return json_util.dumps({"error": str(e)}), 500
