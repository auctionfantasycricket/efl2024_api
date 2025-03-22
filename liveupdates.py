import requests
from pymongo import UpdateOne, UpdateMany
from flask import Blueprint, request
from config import db, app
from datetime import datetime, timezone, timedelta


liveupdates_bp = Blueprint('liveupdates', __name__)


@liveupdates_bp.route('/update_score_from_mycric', methods=['POST'])
def update_score_from_mycric():
    matchid = get_global_data('last-match-id')
    gameday_data = fetch_api_data(matchid)
    update_player_points_in_db(gameday_data)
    update_owner_points_and_rank()
    update_timestamps('pointsUpdatedAt')
    '''
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
    '''
    return 'OK', 200


def get_global_data(attribute_name):
    global_collection = db['global_data']
    document = global_collection.find_one({})
    return document[attribute_name]


def update_timestamps(attribute_name):
    pst_tz = timezone(timedelta(hours=-7))
    # Get the current date and time
    now = datetime.now(pst_tz)
    timestamp_str = now.strftime("%B %d, %Y at %I:%M%p").replace(" 0", " ")
    globalCollection = db['global_data']
    globalCollection.update_one(
        {}, {"$set": {attribute_name: timestamp_str}})


def fetch_api_data(matchid):
    """Fetch data from the API."""
    url = "https://fantasy.iplt20.com/classic/api/feed/live/gamedayplayers"
    params = {
        "lang": "en",
        "tourgamedayId": matchid,
        "teamgamedayId": matchid,
        "liveVersion": 14,
        "announcedVersion": "03222025144453"
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        raise Exception(
            f"Failed to retrieve data. Status Code: {response.status_code}")

    return response.json()


def update_owner_points_and_rank():
    owners_points = {}
    league_ids = set()  # To store unique leagueIds for which points need to be updated

    # Step 1: Gather points for each owner in each league
    players = db.leagueplayers.find({"status": "sold"})
    for player in players:
        owner_name = player.get('ownerTeam')
        league_id = player.get('leagueId')
        today_points = player.get('todayPoints', 0)
        if isinstance(today_points, dict):
            today_points = 0

        if (owner_name, league_id) not in owners_points:
            owners_points[(owner_name, league_id)] = 0

        # Update points for owner within the specific league
        owners_points[(owner_name, league_id)] += today_points

        # Track the leagueId for which we need to update data
        league_ids.add(league_id)

    # Step 2: Update points for each owner in the relevant leagues
    bulk_updates = []
    for league_id in league_ids:
        owners_in_league = db.teams.find({"leagueId": league_id})

        for owner in owners_in_league:
            owner_name = owner.get('teamName')

            # Get points for this owner in the current league
            owner_points = owners_points.get((owner_name, league_id), 0)
            owner_total_points = owner.get('yesterdayPoints', 0) + owner_points

            print(owner_name, owner_points, owner_total_points)

            # Add bulk update operation
            bulk_updates.append(
                UpdateOne(
                    {"teamName": owner_name, "leagueId": league_id},
                    {"$set": {"todayPoints": owner_points, "totalPoints": owner_total_points
                              }}
                )
            )

    # Execute bulk update operations
    if bulk_updates:
        db.teams.bulk_write(bulk_updates)

    print("Owners data updated successfully.")


def update_player_points_in_db(gameday_data):
    """Collect update operations and execute them in bulk."""
    api_players = gameday_data["Data"]["Value"]["Players"]
    bulk_operations = []

    for player in api_players:
        player_name = player["Name"]
        today_points = player.get("GamedayPoints", 0)
        total_points = player.get("OverallPoints", 0)
        print(player_name, today_points, total_points)

        # Create a bulk update operation for each player
        bulk_operations.append(UpdateMany(
            {
                "player_name": player_name,
                "status": "sold"  # Only update players with status "sold"
            },  # Match by player name
            # Set or update points
            {"$set": {"todayPoints":
                      today_points, "points": total_points}},
            upsert=False  # Only update existing documents, don't insert new ones
        ))

    if bulk_operations:
        result = db.leagueplayers.bulk_write(bulk_operations)
        print(
            f"Bulk Update: Matched {result.matched_count} documents and modified {result.modified_count} documents.")
    else:
        print("No bulk operations to perform.")


# Main function to execute the updates


'''
def main(db):
    """Main function to execute the process."""
    try:
        gameday_data = fetch_api_data()  # Fetch API data
        # Update players in DB using bulk operations
        update_player_points_in_db(db, gameday_data)
    except Exception as e:
        print(f"Error: {e}")


# Example usage:
# Assuming `db` is your MongoDB database connection
main(db)
'''
# update_owner_points_and_rank()
