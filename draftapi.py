from flask import Blueprint, request
from config import db
from bson import ObjectId, json_util


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
        ownercollection = request.args.get(
            'ownerCollectionName', 'eflDraft_ownerTeams')

        ownercollection = db[ownercollection]

        update_owner_data(updated_data, ownercollection, player_data)

    return json_util.dumps(result.raw_result)
