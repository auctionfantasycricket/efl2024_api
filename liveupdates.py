import requests
from pymongo import UpdateOne, UpdateMany, DESCENDING
from flask import Blueprint
from config import db, DRAFT_LEAGUE_ID, AUCTION_LEAGUE_ID
from utils import get_global_data
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import re


liveupdates_bp = Blueprint('liveupdates', __name__)


@liveupdates_bp.route('/eod_update_rank_mycric', methods=['POST'])
def eod_update_rank_mycric():
    ownerCollection = db.teams

    # Get all unique leagueIds
    league_ids = ownerCollection.distinct("leagueId")

    bulk_updates = []  # List to store bulk update operations

    for league_id in league_ids:
        # Fetch teams in this league, sorted by totalPoints (descending)
        documents = list(ownerCollection.find(
            {"leagueId": league_id}).sort("totalPoints", DESCENDING))

        rank = 1  # Initialize rank counter for this league

        for document in documents:
            document_id = document["_id"]
            standings = document.get("standings", [])
            standings.append(rank)
            print(document['teamName'], rank, standings)

            # Add update operation to bulk list
            bulk_updates.append(
                UpdateOne(
                    {"_id": document_id},
                    {"$set": {"rank": rank}, "$push": {"standings": rank}}
                )
            )

            rank += 1

    # Execute bulk updates if there are any
    if bulk_updates:
        ownerCollection.bulk_write(bulk_updates)
    eod_update_score_yesterdayPoints()
    update_timestamps('rankingsUpdatedAt')
    increment_match_id()
    update_unsold_player_points_in_db()
    backup()
    return "OK", 200


@liveupdates_bp.route('/eod_update_yesterdayPoints', methods=['POST'])
def eod_update_score_yesterdayPoints():
    ownerCollection = db.teams
    owners = ownerCollection.find()

    bulk_updates = []
    for owner in owners:
        total_points = owner.get('totalPoints', 0)
        print('yest', owner['teamName'], total_points)
        bulk_updates.append(
            UpdateOne(
                {"_id": owner["_id"]},
                {"$set": {"yesterdayPoints": total_points}}
            )
        )

    # Perform bulk update if there are updates to apply
    if bulk_updates:
        ownerCollection.bulk_write(bulk_updates)

    return 'OK', 200


@liveupdates_bp.route('/update_score_from_mycric', methods=['POST'])
def update_score_from_mycric():
    matchid = get_global_data('last-match-id')
    gameday_data = fetch_api_data(matchid)
    update_player_points_in_db(gameday_data)
    update_owner_points_and_rank()
    update_timestamps('pointsUpdatedAt')

    return 'OK', 200


def increment_match_id():
    from datetime import timezone as tz, timedelta
    IST = timedelta(hours=5, minutes=30)
    tomorrow = (datetime.now(tz.utc) + IST + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_count = db.schedule.count_documents({"date": tomorrow})
    increment_by = tomorrow_count if tomorrow_count > 0 else 1

    global_collection = db["global_data"]
    last_match_id = get_global_data("last-match-id")
    new_match_id = last_match_id + increment_by

    global_collection.update_one(
        {}, {"$set": {"last-match-id": new_match_id}}, upsert=True)
    print(f"updated match id by {increment_by} (tomorrow has {tomorrow_count} matches) → {new_match_id}")


# get_global_data is now imported from utils.py


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
        "liveVersion": 16,
        "announcedVersion": "03282026145309"
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
    special_ops = []

    # Build player_name -> _id map from master collection (new schema: no player_name in leagueplayers)
    player_name_to_id = {
        p["player_name"]: p["_id"]
        for p in db.players.find({}, {"player_name": 1})
    }

    # Build transfer_points_map keyed by (leagueId, playerId)
    transfer_points_map = {}
    special_league_players = db.leagueplayers.find(
        {"leagueId": {"$in": [DRAFT_LEAGUE_ID, AUCTION_LEAGUE_ID]}, "status": "sold"},
        {"playerId": 1, "transferredPoints": 1, "leagueId": 1}
    )
    for player in special_league_players:
        transfer_points_map[(player["leagueId"], player["playerId"])] = player.get(
            "transferredPoints", 0)

    for player in api_players:
        player_name = player["Name"]
        today_points = player.get("GamedayPoints", 0)
        total_points = player.get("OverallPoints", 0)

        player_id = player_name_to_id.get(player_name)
        if not player_id:
            continue  # Player not in master, skip

        print(player_name, today_points, total_points)

        bulk_operations.append(UpdateMany(
            {
                "playerId": player_id,
                "status": "sold",
                "leagueId": {"$nin": [DRAFT_LEAGUE_ID, AUCTION_LEAGUE_ID]}
            },
            {"$set": {"todayPoints": today_points, "points": total_points}},
            upsert=False
        ))

        for league_id in [DRAFT_LEAGUE_ID, AUCTION_LEAGUE_ID]:
            special_ops.append(UpdateOne(
                {
                    "playerId": player_id,
                    "status": "sold",
                    "leagueId": league_id
                },
                {
                    "$set": {
                        "todayPoints": today_points,
                        "points": total_points - transfer_points_map.get((league_id, player_id), 0)
                    }
                },
                upsert=False
            ))

    if bulk_operations:
        result = db.leagueplayers.bulk_write(bulk_operations)
        print(f"Bulk Update: Matched {result.matched_count} documents and modified {result.modified_count} documents.")
    else:
        print("No bulk operations to perform.")

    if special_ops:
        result = db.leagueplayers.bulk_write(special_ops)
        print(f"Special Update: Matched {result.matched_count} documents and modified {result.modified_count} documents.")
    else:
        print("No special operations to perform.")


def update_unsold_player_points_in_db():
    """Collect update operations and execute them in bulk."""
    matchid = get_global_data('last-match-id')
    gameday_data = fetch_api_data(matchid)
    api_players = gameday_data["Data"]["Value"]["Players"]
    bulk_operations = []

    # Build player_name -> _id map from master collection
    player_name_to_id = {
        p["player_name"]: p["_id"]
        for p in db.players.find({}, {"player_name": 1})
    }

    for player in api_players:
        player_name = player["Name"]
        today_points = player.get("GamedayPoints", 0)
        total_points = player.get("OverallPoints", 0)

        player_id = player_name_to_id.get(player_name)
        if not player_id:
            continue

        print(player_name, today_points, total_points)

        bulk_operations.append(UpdateMany(
            {
                "playerId": player_id,
                "status": {"$ne": "sold"},
                "leagueId": {"$in": [DRAFT_LEAGUE_ID, AUCTION_LEAGUE_ID]}
            },
            {"$set": {"todayPoints": today_points, "points": total_points}},
            upsert=False
        ))

    if bulk_operations:
        result = db.leagueplayers.bulk_write(bulk_operations)
        print(f"Bulk Update: Matched {result.matched_count} documents and modified {result.modified_count} documents.")
    else:
        print("No bulk operations to perform.")


def backup():
    # Get current date in YYYYMMDD format
    today_date = datetime.now().strftime("%Y%m%d")

    # Identify and remove all old backup collections
    for collection_name in db.list_collection_names():
        # Matches collections ending with _YYYYMMDD
        if re.search(r'_\d{8}$', collection_name):
            db[collection_name].drop()
            print(f"Removed old backup: {collection_name}")

    # Create fresh backups only for original collections (excluding backups)
    for collection_name in db.list_collection_names():
        # Skip already backed-up collections
        if not re.search(r'_\d{8}$', collection_name):
            new_collection_name = f"{collection_name}_{today_date}"
            db[collection_name].aggregate([{"$out": new_collection_name}])
            print(
                f"Copied collection {collection_name} to {new_collection_name}")

    print("Old backups removed, and new backup created successfully.")


# eod_update_rank_mycric()
# update_unsold_player_points_in_db()
# update_score_from_mycric()
# backup()


def fix_all_team_points_total_only():
    # Step 1: Get all leagueIds where at least one player is sold
    league_ids = db.leagueplayers.distinct("leagueId", {"status": "sold"})

    for league_id in league_ids:
        # Step 2: Aggregate points by team from sold players
        pipeline = [
            {
                "$match": {
                    "leagueId": league_id,
                    "status": "sold"
                }
            },
            {
                "$group": {
                    "_id": "$ownerTeam",
                    "totalPoints": {"$sum": "$points"}
                }
            }
        ]

        player_points = {
            doc["_id"]: doc["totalPoints"]
            for doc in db.leagueplayers.aggregate(pipeline)
        }

        # Step 3: Add transfer history points from teams
        teams = db.teams.find({"leagueId": league_id})
        for team in teams:
            team_name = team["teamName"]
            transfer_points = sum(entry.get("points", 0)
                                  for entry in team.get("transferHistory", []))

            new_total = player_points.get(team_name, 0) + transfer_points

            result = db.teams.update_one(
                {"_id": team["_id"]},
                {"$set": {
                    "totalPoints": new_total,
                    "yesterdayPoints": new_total
                }}
            )

            print(
                f"[{league_id}] {team_name}: totalPoints={new_total} (updated {result.modified_count})")


# look at today points for both leagues, all players and set it to zero, and reduce that from total team points and yesterday points


def fix_pbks_dc_game():
    league_ids = [DRAFT_LEAGUE_ID, AUCTION_LEAGUE_ID]

    league_names = {
        str(DRAFT_LEAGUE_ID): "DRAFT LEAGUE",
        str(AUCTION_LEAGUE_ID): "AUCTION LEAGUE"
    }

    for league_id in league_ids:
        print(f"\n{league_names[str(league_id)]}")
        teams = db.teams.find({"leagueId": league_id})
        for team in teams:
            team_name = team["teamName"]
            players = list(db.leagueplayers.find(
                {"ownerTeam": team_name, "leagueId": league_id, "todayPoints": {"$ne": 0}}
            ))

            if not players:
                continue

            print(f"\n{team_name}")
            total_deduction = 0
            for player in players:
                # Look up player_name from master via playerId
                player_meta = db.players.find_one({"_id": player["playerId"]}, {"player_name": 1})
                player_name = player_meta["player_name"] if player_meta else str(player["playerId"])
                today_points = player["todayPoints"]
                print(f"{player_name} - {today_points}")
                total_deduction += today_points

                # reduce today's Points from leagueplayers points and set today's points to 0
                db.leagueplayers.update_one(
                    {"_id": player["_id"]},
                    {"$set": {
                        "points": player["points"] - today_points,
                        "todayPoints": 0
                    }}
                )
                print(f"Updated {player_name} points to {player['points'] - today_points}")
                
                

            before = team["totalPoints"]
            after = before - total_deduction
            print(f"\ntotal points deducted = {total_deduction}")
            print(f"Before = {before}")
            print(f"After = {after}")

            
            db.teams.update_one(
                {"_id": team["_id"]},
                {"$set": {
                    "totalPoints": after,
                    "yesterdayPoints": after
                }}
            )
            


#fix_pbks_dc_game()