from pymongo import MongoClient
from bson.objectid import ObjectId
from config import db
from datetime import datetime, timedelta
from bson import ObjectId, json_util


def drop_draft_player(input_player, leagueid):
    # Get player information from leagueplayers collection
    player_collection = db.leagueplayers
    id_filter = {"player_name": input_player, "leagueId": ObjectId(leagueid)}
    player_data = player_collection.find_one(id_filter)

    if not player_data:
        print({"error": "Player not found"})

    owner_team = player_data.get("ownerTeam", "")
    player_name = player_data.get("player_name", "")
    points = player_data.get("points", 0)
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

    owner_query = {"teamName": owner_team, "leagueId": ObjectId(leagueid)}
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

    print(
        f"Updating team {owner_team}: reducing totalCount, role-specific counts, and foreign player count if applicable.")
    owner_collection.update_one({"_id": owner["_id"]}, {"$set": owner})

    print({"message": "Player successfully dropped and database updated."})


def draftplayer(pick, owner_team, leagueId):
    player_name = pick  # Assuming pick contains the player's name

    # Get collection names
    collection_name = 'leagueplayers'
    owner_collection_name = 'teams'

    playerCollection = db[collection_name]
    player_data = playerCollection.find_one(
        {"player_name": player_name, "leagueId": ObjectId(leagueId)})

    if player_data is None:
        return json_util.dumps({"error": "Player not found"}), 404

    updated_data = {}

    today_points = 0

    # Add 'todayPoints' to updated_data
    updated_data["todayPoints"] = today_points
    updated_data["transferredPoints"] = player_data.get('points', 0)
    updated_data['status'] = 'sold'
    updated_data['ownerTeam'] = owner_team

    # Update player record in the database
    result = playerCollection.update_one(
        {"player_name": player_name, "leagueId": ObjectId(leagueId)}, {"$set": updated_data})

    # Update the owner's data accordingly
    owner_collection = db[owner_collection_name]
    update_owner_data(owner_team, owner_collection, player_data, leagueId)

    # Return a success message
    return json_util.dumps({"message": "Player drafted successfully"})


def update_owner_data(owner_team, ownercollection, player_data, league_id):

    myquery = {"teamName": owner_team, "leagueId": ObjectId(str(league_id))}
    owners_data = ownercollection.find(myquery)

    for owner_items in owners_data:
        owner_items = update_owner_items(owner_items, player_data)

        # Update the owner's data in the database
        filter_owner = {"_id": ObjectId(str(owner_items["_id"]))}
        ownercollection.update_one(filter_owner, {"$set": owner_items})
        print(f"Owner data updated: {owner_items}")


def update_owner_items(owner_items, player_data):

    owner_items["totalCount"] += 1
    print(f"Total count updated: {owner_items['totalCount']}")

    role = player_data["player_role"].upper()
    if role == "BATTER":
        owner_items["batCount"] += 1
        print(f"Bat count updated: {owner_items['batCount']}")
    elif role == "BOWLER":
        owner_items["ballCount"] += 1
        print(f"Ball count updated: {owner_items['ballCount']}")
    elif role == "ALL_ROUNDER":
        owner_items["arCount"] += 1
        print(f"All-rounder count updated: {owner_items['arCount']}")
    else:
        print("Role not found")

    if player_data["isOverseas"]:
        owner_items["fCount"] += 1
        print(f"Foreign player count updated: {owner_items['fCount']}")

    return owner_items


def is_before_auction_deadline(db):
    # Get current UTC time
    current_time_utc = datetime.utcnow()

    # Convert to PDT (UTC - 7, since April 6 is during daylight saving)
    current_time_pdt = current_time_utc - timedelta(hours=7)

    # Fetch the deadline string
    global_data = db.global_data.find_one({}, {"nextAuctionDeadline": 1})

    if not global_data or 'nextAuctionDeadline' not in global_data:
        raise ValueError("nextAuctionDeadline not found in global_data")

    # Parse the deadline string: "April 6, 2025 at 1:00PM (PST)"
    deadline_str = global_data['nextAuctionDeadline']
    # Remove the timezone part for parsing
    cleaned_str = deadline_str.replace(" (PST)", "").replace(" (PDT)", "")

    # Parse the cleaned string into a datetime object
    deadline_dt = datetime.strptime(cleaned_str, "%B %d, %Y at %I:%M%p")

    # Compare current PDT time to parsed deadline
    return current_time_pdt < deadline_dt


def print_test():
    print('what a wow')

#draftplayer("Zeeshan Ansari", "Dads Of Pitches", "67da30b26a17f44a19c2241a")
#drop_draft_player_backupdb('Adam Zampa', '67d4dd408786c3e1b4ee172a')


def duplicate_player_to_leagues(
    db,
    league_ids: list,
    original_player_name: str,
    new_player_name: str,
    new_player_role: str,
    new_ipl_team_name: str,
    new_is_overseas: bool
):
    leagueplayers = db.leagueplayers

    for league_id in league_ids:
        # Find the original player document in this league
        original_doc = leagueplayers.find_one({
            "leagueId": ObjectId(league_id),
            "player_name": original_player_name
        })

        if not original_doc:
            print(
                f"Original player '{original_player_name}' not found in league {league_id}")
            continue

        # Remove _id for insertion
        original_doc.pop('_id')

        # Update the fields for the new player
        original_doc.update({
            "player_name": new_player_name,
            "player_role": new_player_role,
            "ipl_team_name": new_ipl_team_name,
            "isOverseas": new_is_overseas,
            "points": 0,
            "totalPoints": 0,
            "ownerTeam": "",
            "status": "unsold",
            "boughtFor": 0,
            # make sure leagueId is set correctly
            "leagueId": ObjectId(league_id)
        })

        result = leagueplayers.insert_one(original_doc)
        print(
            f"Inserted '{new_player_name}' into league {league_id} with ID: {result.inserted_id}")


league_ids = [ObjectId("67da30b26a17f44a19c2241a"),
              ObjectId("67d4dd408786c3e1b4ee172a")]
'''
# Dewald Brevis replaces Gurjapneet Singh
duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Gurjapneet Singh",
    new_player_name="Dewald Brevis",
    new_player_role="BATTER",
    new_ipl_team_name="Chennai Super Kings",
    new_is_overseas=True
)

# Dasun Shanaka replaces Glenn Phillips
duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Glenn Phillips",
    new_player_name="Dasun Shanaka",
    new_player_role="ALLROUNDER",
    new_ipl_team_name="Gujarat Titans",
    new_is_overseas=True
)

# Aayush Mhatre replaces Ruturaj Gaikwad
duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Ruturaj Gaikwad",
    new_player_name="Aayush Mhatre",
    new_player_role="BATTER",
    new_ipl_team_name="Chennai Super Kings",
    new_is_overseas=False
)

# Smaran Ravichandran replaces Adam Zampa
duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Adam Zampa",
    new_player_name="Smaran Ravichandran",
    new_player_role="BATTER",
    new_ipl_team_name="Sunrisers Hyderabad",
    new_is_overseas=False
)


duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Tim Seifert",
    new_player_role="BATTER",
    new_ipl_team_name="Royal Challengers Bangalore",
    new_is_overseas=True
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Blessing Muzarabani",
    new_player_role="BOWLER",
    new_ipl_team_name="Royal Challengers Bangalore",
    new_is_overseas=True
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Mayank Agarwal",
    new_player_role="BATTER",
    new_ipl_team_name="Royal Challengers Bangalore",
    new_is_overseas=False
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Jonny Bairstow",
    new_player_role="BATTER",
    new_ipl_team_name="Mumbai Indians",
    new_is_overseas=True
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Richard Gleeson",
    new_player_role="BOWLER",
    new_ipl_team_name="Mumbai Indians",
    new_is_overseas=True
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Charith Asalanka",
    new_player_role="BATTER",
    new_ipl_team_name="Mumbai Indians",
    new_is_overseas=True
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Mujeeb Ur Rahman",
    new_player_role="BOWLER",
    new_ipl_team_name="Mumbai Indians",
    new_is_overseas=True
)



duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Nandre Burger",
    new_player_role="BOWLER",
    new_ipl_team_name="Rajasthan Royals",
    new_is_overseas=True
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Lhuan-dre Pretorius",
    new_player_role="BATTER",
    new_ipl_team_name="Rajasthan Royals",
    new_is_overseas=True
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Mustafizur Rahman",
    new_player_role="BOWLER",
    new_ipl_team_name="Delhi Capitals",
    new_is_overseas=True
)


duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Harsh Dubey",
    new_player_role="BOWLER",
    new_ipl_team_name="Sunrisers Hyderabad",
    new_is_overseas=False
)

duplicate_player_to_leagues(
    db=db,
    league_ids=league_ids,
    original_player_name="Musheer Khan",
    new_player_name="Urvil Patel",
    new_player_role="BATTER",
    new_ipl_team_name="Chennai Super Kings",
    new_is_overseas=False
)
'''