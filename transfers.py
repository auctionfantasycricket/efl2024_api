from config import db, AUCTION_LEAGUE_ID
from utils import push_waiver_to_history_and_reset, _drop_player_core, update_role_counts
from bson import ObjectId
import base64
from flask import Blueprint, jsonify
from datetime import datetime


leagueId = AUCTION_LEAGUE_ID

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

            # Get first two players from out list, or empty strings if missing
            released_players = [
                base64.b64decode(out_players[i]).decode(
                    'utf-8') if len(out_players) > i and out_players[i] != '' else ""
                for i in range(2)
            ]

            added_purse = 0
            for released_player in released_players:
                if released_player != "":
                    print('dropping player', released_player)
                    added_purse += drop_auction_player(released_player)

            release_details.append({
                'teamName': team_name,
                'releasedPlayers': released_players,
                'remainingPurse': current_purse + added_purse,
                'order': idx + 1  # Order starts from 1
            })
        # print(release_details)
        db.leagues.update_one({"_id": leagueId}, {
                              "$set": {'releaseDetails': release_details}})
        push_waiver_to_history_and_reset(str(AUCTION_LEAGUE_ID))  # auction

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def drop_auction_player(input_player):
    player_collection = db.leagueplayers
    id_filter = {"player_name": input_player, "leagueId": leagueId}
    player_data = player_collection.find_one(id_filter)

    if not player_data:
        print({"error": f"Player not found: {input_player}"})
        return 0

    owner_team = player_data.get("ownerTeam", "")
    owner_collection = db.teams
    owner = owner_collection.find_one({"teamName": owner_team, "leagueId": leagueId})

    if not owner:
        print({"error": "Owner team not found"})
        return 0

    bought_for = _drop_player_core(player_data, player_collection, id_filter, owner)

    if not update_role_counts(owner, player_data.get("player_role", ""), -1):
        print("Role not found")
    if player_data.get("isOverseas"):
        owner["fCount"] -= 1

    # Auction-specific: refund purse and recalculate maxBid
    owner['currentPurse'] += bought_for
    owner['maxBid'] = owner['currentPurse'] - 20 * (14 - owner['totalCount'])

    owner_collection.update_one({"_id": owner["_id"]}, {"$set": owner})
    print({"message": "Player successfully dropped and database updated."})
    return bought_for


# push_waiver_to_history_and_reset is now imported from utils.py
