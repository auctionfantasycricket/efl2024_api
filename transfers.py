from config import db
from bson import ObjectId
import base64
from flask import Blueprint, jsonify
from datetime import datetime


leagueId = ObjectId('67d4dd408786c3e1b4ee172a')

transfers_bp = Blueprint('transfers', __name__)


@transfers_bp.route('/generate_release_details', methods=['POST'])
def generate_release_details():
    try:

        # Fetch teams from the database
        teams_cursor = db.teams.find({'leagueId': leagueId})
        teams = list(teams_cursor)

        # Sort by totalPoints (ascending = lowest score gets first pick)
        teams.sort(key=lambda x: x.get('totalPoints', 0))

        release_details = []

        for idx, team in enumerate(teams):
            team_name = team.get('teamName', 'Unnamed Team')
            current_purse = team.get('currentPurse', 0)
            current_waiver = team.get('currentWaiver', {})
            out_players = current_waiver.get('out', [])

            # Get first player from out list, or empty string if missing
            released_player = base64.b64decode(
                out_players[0]).decode('utf-8') if out_players and out_players[0] != '' else ""
            if released_player != "":
                print('dropping player')

                added_purse = drop_auction_player(released_player)
            else:
                added_purse = 0

            release_details.append({
                'teamName': team_name,
                'releasedPlayers': [released_player],
                'remainingPurse': current_purse+added_purse,
                'order': idx + 1  # Order starts from 1
            })

        db.leagues.update_one({"_id": leagueId}, {
                              "$set": {'releaseDetails': release_details}})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def drop_auction_player(input_player):
    # Get player information from leagueplayers collection
    player_collection = db.leagueplayers
    id_filter = {"player_name": input_player, "leagueId": leagueId}
    player_data = player_collection.find_one(id_filter)

    if not player_data:
        print({"error": "Player not found"})

    owner_team = player_data.get("ownerTeam", "")
    player_name = player_data.get("player_name", "")
    points = player_data.get("points", 0)
    boughtFor = player_data.get('boughtFor', 0)
    transfer_date = datetime.now().strftime("%d %B, %Y")

    update_data = {
        "$set": {
            "ownerTeam": "",
            "status": "unsold-dropped",
        }
    }

    print(
        f"Updating player {player_name}: setting ownerTeam to empty, status to 'unsold-dropped', and resetting points.")
    player_collection.update_one(id_filter, update_data)

    owner_query = {"teamName": owner_team, "leagueId": leagueId}
    owner_collection = db.teams
    owner = owner_collection.find_one(owner_query)

    if not owner:
        return print({"error": "Owner team not found"})

    transfer_history_entry = {
        "player_name": player_name,
        "points": points,
        "transfer_date": transfer_date,
    }

    if "transferHistory" not in owner:
        owner["transferHistory"] = [transfer_history_entry]
    else:
        owner["transferHistory"].append(transfer_history_entry)

    print(
        f"Adding transfer history for player {player_name} to team {owner_team}.")

    owner["totalCount"] -= 1

    role = player_data.get("player_role", "")
    if role == "BATTER":
        owner["batCount"] -= 1
    elif role == "BOWLER":
        owner["ballCount"] -= 1
    elif role == "ALL_ROUNDER":
        owner["arCount"] -= 1
    else:
        print("Role not found")

    if player_data["isOverseas"]:
        owner["fCount"] -= 1
    owner['currentPurse'] += boughtFor
    print(
        f"Updating team {owner_team}: reducing totalCount, role-specific counts, and foreign player count if applicable.")
    owner_collection.update_one({"_id": owner["_id"]}, {"$set": owner})

    print({"message": "Player successfully dropped and database updated."})
    return boughtFor
