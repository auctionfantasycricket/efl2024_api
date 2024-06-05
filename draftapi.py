from flask import Blueprint, request
from config import db
from bson import ObjectId, json_util
from datetime import datetime, timedelta
from collections import deque
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import hashlib


import base64
import json


draftapi_bp = Blueprint('draftapi', __name__)


def update_owner_data(updated_data, ownercollection, player_data):
    owner_team = updated_data['ownerTeam']
    myquery = {"teamName": owner_team}
    owners_data = ownercollection.find(myquery)

    for owner_items in owners_data:
        owner_items = update_owner_items(
            owner_items, player_data)
        filter_owner = {"_id": ObjectId(str(owner_items["_id"]))}
        ownercollection.update_one(filter_owner, {"$set": owner_items})


def update_owner_items(owner_items, player_data):

    owner_items["totalCount"] += 1

    role = player_data["player_role"]
    if role == "batter":
        owner_items["batCount"] += 1
    elif role == "bowler":
        owner_items["ballCount"] += 1
    elif role == "allrounder":
        owner_items["arCount"] += 1
    elif role == "wicketkeeper":
        owner_items["batCount"] += 1
        owner_items["wkCount"] += 1
    else:
        print("Role not found")

    associate_nations = ["Canada", "Namibia", "Nepal", "Netherlands", "Oman",
                         "Papua-new-guinea", "Scotland", "Uganda", "United-states-of-america", "Ireland"]

    if player_data["country"] in associate_nations:
        owner_items["fCount"] += 1

    # Iterate through draftSequence to find the first empty string and update it
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


def update_current_waiver(email, current_waiver, owner_collection_name):
    team_owners = db[owner_collection_name]
    result = team_owners.update_one(
        {'emails': email},
        {'$set': {'currentWaiver': current_waiver}}
    )
    return result.modified_count > 0


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


def get_teams_and_sort():
    # 1 Get Teams
    owner_collection_name = request.args.get(
        'ownerCollectionName', 'eflDraft_ownerTeams_backup')
    ownercollection = db[owner_collection_name]
    allDocs = ownercollection.find().sort('rank', -1)
    docs_dict = {}
    docs_list = []

    for doc in allDocs:
        teamName = doc["teamName"]
        docs_dict[teamName] = {'in': [], 'out': []}
        docs_dict[teamName]['in'].extend(doc["currentWaiver"]["in"])
        # decrypt_arr(doc["currentWaivers"]["in"]))
        docs_dict[teamName]['out'].extend(doc["currentWaiver"]["out"])
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
        return True

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
        tempBallCount += 1

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
        tempBallCount -= 1

    if tempBatCount >= 4 and tempBallCount >= 4 and tempARCount >= 1 and tempWKCount >= 1 and tempFCount >= 2:
        return True
    else:
        return False


def check_criteria(teamName, teamdict, playerName, outArr):
    outRet = ''
    success = False
    for i, o in enumerate(outArr):
        if o == 'X':
            continue
        if swap_possible(teamName, teamdict, playerName, o):
            outRet = o
            outArr[i] = 'X'
            success = True
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

    for i in range(4):
        obj = {'pref': i+1, 'picks': [], 'result': [], 'reason': []}
        for teamToProcess in orders[i]:
            # in, out = decrypt_waivers(docs_dict[teamtoProcess])

            playerToProcess = docs_dict[teamToProcess]['in'][i]
            obj['picks'].append(teamToProcess + ' -> ' + playerToProcess)
            if playerToProcess == '':
                obj['result'].append('Fail')
                obj['reason'].append('empty player')
                continue
            if playerToProcess in playersTaken:
                obj['result'].append('Fail')
                obj['reason'].append(playerToProcess + ' already taken')
                continue
            if len(teamPlayersIn[teamToProcess]) == 2:
                obj['result'].append('Fail')
                obj['reason'].append(teamToProcess + ' already picked up 2')
                continue
            satisfied, outPlayer, docs_dict[teamToProcess]['out'] = check_criteria(
                teamToProcess, docs_dict, playerToProcess, docs_dict[teamToProcess]['out'])
            if not satisfied:
                obj['result'].append('Fail')
                obj['reason'].append('getting ' + playerToProcess + ' and dropping ' +
                                     outPlayer + ' breaks team restriction condition')
            else:
                obj['result'].append('Successful')
                obj['reason'].append(
                    teamToProcess+' gets ' + playerToProcess + ' and drops ' + outPlayer)
                teamPlayersIn[teamToProcess].append(playerToProcess)
                teamPlayersOut[teamToProcess].append(outPlayer)
                playersTaken.add(playerToProcess)

        results.append(obj)
    print(results)
    return results


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


@draftapi_bp.route('/updateCurrentWaiver/<email>', methods=['PUT'])
def update_current_waiver_api(email):
    try:
        owner_collection_name = request.args.get(
            'ownerCollectionName', 'eflDraft_ownerTeams')
        current_waiver = request.json.get('currentWaiver')

        # Validate currentWaiver data
        is_valid, validation_message = validate_waiver_data(current_waiver)
        if not is_valid:
            response = json_util.dumps({'error': validation_message})
            return response, 400

        # Add lastUpdatedBy and lastUpdatedTime
        current_waiver['lastUpdatedBy'] = email
        # Get the current UTC time
        now_utc = datetime.utcnow()

        # Calculate the PST time (UTC-8)
        pst_offset = timedelta(hours=-7)
        now_pst = now_utc + pst_offset

        # Format the time as required
        current_waiver['lastUpdatedTime'] = now_pst.strftime(
            '%dth %B at %I:%M:%S %p')

        if update_current_waiver(email, current_waiver, owner_collection_name):
            response = json_util.dumps(
                {'message': 'Current waiver updated successfully'})
            return response, 200
        else:
            response = json_util.dumps(
                {'error': 'No team owner found for the provided email'})
            return response, 404
    except Exception as e:
        response = json_util.dumps({'error': str(e)})
        return response, 500


@draftapi_bp.route('/draftplayer/<_id>', methods=['PUT'])
def draftplayer(_id):
    updated_data = request.get_json()
    filter = {"_id": ObjectId(str(_id))}

    # Get the collectionName from the query parameter
    collection_name = request.args.get(
        'collectionName', 'eflDraft_playersCentral')

    playerCollection = db[collection_name]
    # Get the collectionName from the query parameter
    player_data = playerCollection.find_one(filter)
    if player_data is None:
        return json_util.dumps({"error": "Player not found"}), 404

    # Exclude _id from update_data to avoid updating it
    updated_data.pop('_id', None)
    result = playerCollection.update_one(filter, {"$set": updated_data})

    if updated_data['status'].lower() == "sold":
        ownercollectionName = request.args.get(
            'ownerCollectionName', 'eflDraft_ownerTeams')

        ownercollection = db[ownercollectionName]

        update_owner_data(updated_data, ownercollection, player_data)

    return json_util.dumps(result.raw_result)
