from bson.objectid import ObjectId
from bson import ObjectId
from config import db
import random
import base64
import binascii
from flask import Blueprint, jsonify
import add_drop


# Existing functions...
waivers_bp = Blueprint('transfers', __name__)


def get_teams_sorted_by_rank(league_id):
    """Fetch teams in the league and sort them by rank in descending order (lowest rank first)."""
    teams = list(db.teams.find(
        {"leagueId": ObjectId(league_id)}).sort("rank", -1))
    return teams


def generate_waiver_order(teams, rounds=4):
    """Generate the waiver order for the given number of rounds."""
    order = []
    for i in range(rounds):
        rotated_teams = teams[i:] + teams[:i]
        order.append([team["teamName"] for team in rotated_teams])
    return order


def is_valid(pick, drop, taken_players, unswappable_players, round_num):
    """Validate the pick and drop logic based on different conditions."""
    if not pick and not drop:
        return "ND", "No Drop"  # No drop provided
    if not pick:
        return "NP", "No Pick"  # No pick provided
    if pick in taken_players:
        return "PT", "Pick Taken"  # Player already taken
    if pick in unswappable_players or drop in unswappable_players:
        return "SW", "Unswappable"  # Player is unswappable
    if round_num == 4 and drop:
        return "AR", "All Replaced"  # All players replaced in the last round
    return "SW", "Success"  # Swap valid


def get_random_players():
    """Generate random player names for testing."""
    return [f"Player{num}" for num in range(1, 21)]


def get_current_waivers(teams, league_id):
    """Extract current waiver picks and drops dynamically for each team from DB."""
    picks = []
    for team in teams:
        # Fetch the team from the database using teamName and leagueId
        team_data = db.teams.find_one(
            {"teamName": team["teamName"], "leagueId": ObjectId(league_id)})

        # Default values in case the currentWaiver object is not present
        current_waiver_in = []
        current_waiver_out = []

        # Check if the currentWaiver exists and has the required fields
        if team_data and "currentWaiver" in team_data:
            current_waiver_in = team_data["currentWaiver"].get("in", [])
            current_waiver_out = team_data["currentWaiver"].get("out", [])

        # If the arrays are smaller than expected, pad with empty values
        current_waiver_in = current_waiver_in[:4]  # Limit to 4 "in" players
        current_waiver_out = current_waiver_out[:2]  # Limit to 2 "out" players

        pick_data = {
            "team": team["teamName"],
            "drop_index": 0,  # Tracks the index of the drop
            "pick_index": 0,  # Tracks the index of the pick
            "drop": current_waiver_out[0] if current_waiver_out else "",
            "pick": current_waiver_in[0] if current_waiver_in else "",
            "status": "",
            "message": ""
        }
        picks.append(pick_data)

    return picks


def generate_waiver_process(league_id,  generateEmpty=True, rounds=4):
    """Main function to generate waiver process based on league ID."""
    teams = get_teams_sorted_by_rank(league_id)
    waiver_order = generate_waiver_order(teams, rounds)
    print(waiver_order)
    results = generate_waiver_results(waiver_order, generateEmpty)

    return results


def get_waiver_dict(leagueId):

    waiver_dict = {}

    # Fetch all teams in the given league
    teams = db.teams.find({"leagueId": ObjectId(leagueId)}, {
                          "teamName": 1, "currentWaiver": 1, "_id": 0})

    # Populate the dictionary
    for team in teams:
        team_name = team["teamName"]
        current_waiver = team.get(
            "currentWaiver", {"out": ['', ''], "in": ['', '', '', '']})
        waiver_dict[team_name] = current_waiver
        # print('--------', team_name)
        for out1 in current_waiver['out']:
            if out1 != "":
                out1 = base64.b64decode(out1).decode('utf-8')
            # print('outtt', out1)
        for out1 in current_waiver['in']:
            if out1 != "":
                out1 = base64.b64decode(out1).decode('utf-8')
            # print('innn', out1)

    return waiver_dict


def swap_possible(owner_items, nextdrop_data, nextpick_data):
    updated_counts = owner_items.copy()

    drop_role = nextdrop_data["player_role"].upper()
    if drop_role == "BATTER":
        updated_counts["batCount"] -= 1
    elif drop_role == "BOWLER":
        updated_counts["ballCount"] -= 1
    elif drop_role == "ALL_ROUNDER":
        updated_counts["arCount"] -= 1

    if nextdrop_data["isOverseas"]:
        updated_counts["fCount"] -= 1

    pick_role = nextpick_data["player_role"].upper()
    if pick_role == "BATTER":
        updated_counts["batCount"] += 1
    elif pick_role == "BOWLER":
        updated_counts["ballCount"] += 1
    elif pick_role == "ALL_ROUNDER":
        updated_counts["arCount"] += 1

    if nextpick_data["isOverseas"]:
        updated_counts["fCount"] += 1

    if (
        updated_counts["batCount"] < 2 or
        updated_counts["ballCount"] < 2 or
        updated_counts["arCount"] < 2 or
        updated_counts["fCount"] < 1 or
        updated_counts["fCount"] > 3
    ):
        return "failure", "Restriction violated"

    return "success", "Swap possible"


pickedplayers = set()


def get_result(league_id, nextdrop, nextpick, team):
    if not nextpick:
        return "", "No player provided in preference"
    if not nextdrop:
        return "", "No player provided in drop"
    # pickedplayers = set()
    nextdrop_data = db.leagueplayers.find_one(
        {"leagueId": ObjectId(league_id), "player_name": nextdrop},
        {"player_name": 1, "player_role": 1, "isOverseas": 1, "_id": 0}
    )

    nextpick_data = db.leagueplayers.find_one(
        {"leagueId": ObjectId(league_id), "player_name": nextpick},
        {"player_name": 1, "player_role": 1, "isOverseas": 1, "_id": 0}
    )

    if not nextdrop_data or not nextpick_data:
        return "failure", "One or both players not found"

    team_data = db.teams.find_one(
        {"leagueId": ObjectId(league_id), "teamName": team},
        {
            "batCount": 1,
            "ballCount": 1,
            "fCount": 1,
            "arCount": 1,
            "_id": 0
        }
    )

    if not team_data:
        return "failure", "Team or owner data not found"

    owner_items = {
        "batCount": team_data.get("batCount", 0),
        "ballCount": team_data.get("ballCount", 0),
        "fCount": team_data.get("fCount", 0),
        "arCount": team_data.get("arCount", 0)
    }
    if nextpick in pickedplayers:
        return 'failure', 'player was already picked'
    status, message = swap_possible(owner_items, nextdrop_data, nextpick_data)
    if status == "success":
        pickedplayers.add(nextpick)
    return status, message


def do_the_trasnfers(nextdrop, nextpick, team):
    add_drop.draftplayer(nextpick, team, '67da30b26a17f44a19c2241a')
    add_drop.drop_draft_player(nextdrop, '67da30b26a17f44a19c2241a')


def generate_waiver_results(waiver_order, generateEmpty=True):
    waiver_results = []
    dropped_count = {}  # Tracks how many players have been dropped per team
    waiver_dict = get_waiver_dict('67da30b26a17f44a19c2241a')
    for round_num, order in enumerate(waiver_order, start=1):
        round_result = {
            "round": round_num,
            "waiverOrder": order,
            "picks": []
        }

        # Example pick logic (replace with actual logic if needed)
        for team in order:
            nextdrop = "Your Worst performer"
            nextpick = "Your next superstar"
            status = ""
            message = ""
            if not generateEmpty:
                drop_index = dropped_count.get(team, 0)

                nextdrop = '' if (
                    drop_index == 2) else waiver_dict[team]['out'][drop_index]
                nextpick = waiver_dict[team]['in'][round_num-1]
                try:
                    if nextdrop != "":
                        nextdrop = base64.b64decode(nextdrop).decode('utf-8')
                    if nextpick != "":
                        nextpick = base64.b64decode(nextpick).decode('utf-8')
                except binascii.Error:
                    print('pppp', team, nextpick, nextdrop)

                # print(';;;; ', team, round_num, drop_index, nextdrop, nextpick)
                # get_result(nextdrop, nextpick, team
                if drop_index == 2:
                    status, message = "", "All Transferred done"
                else:
                    status, message = get_result(
                        '67da30b26a17f44a19c2241a', nextdrop, nextpick, team)
                if status == "success":
                    dropped_count[team] = drop_index+1
                    do_the_trasnfers(nextdrop, nextpick, team)

            round_result["picks"].append({
                "team": team,
                "drop": nextdrop,  # Placeholder
                "pick": nextpick,  # Placeholder
                "status": status,
                "message": message
            })

        waiver_results.append(round_result)

    return waiver_results


@waivers_bp.route('/final_generate_waiver_results', methods=['POST'])
def final_generate_waiver_results(generateEmpty=True):
    # Example usage:
    waiverResults = generate_waiver_process(
        '67da30b26a17f44a19c2241a', generateEmpty)
    # Call update_one properly by using parentheses
    result = db.leagues.update_one(
        # Find the league by its ID
        {"_id": ObjectId('67da30b26a17f44a19c2241a')},
        # Upsert the waiverResults field
        {"$set": {"waiverResults": waiverResults}},
        upsert=True  # Ensures the document is created if not found
    )
    if not generateEmpty:
        push_waiver_to_history_and_reset('67da30b26a17f44a19c2241a')
    # Print update result details
    print(
        f"Matched: {result.matched_count}, Modified: {result.modified_count}")

    if result.matched_count == 0:
        print(f"No matching league found. A new document may have been created.")
    elif result.modified_count > 0:
        print(
            f"Waiver results successfully updated for league ID: 67da30b26a17f44a19c2241a")
    else:
        print(f"Waiver results were already up to date. No changes made.")


def push_waiver_to_history_and_reset(leagueID):
    # Find all teams with the given leagueID
    teams = db.teams.find({"leagueId": ObjectId(leagueID)})

    for team in teams:
        # Get current waiver
        current_waiver = team.get("currentWaiver", None)

        if current_waiver:
            # Push currentWaiver to waiverHistory (create if it doesn't exist)
            db.teams.update_one(
                {"_id": team["_id"]},
                {"$push": {"waiverHistory": current_waiver},
                 "$set": {"currentWaiver": {"out": ["", ""], "in": ["", "", "", ""]}}}
            )
        else:
            # Just reset currentWaiver if it doesn't exist
            db.teams.update_one(
                {"_id": team["_id"]},
                {"$set": {"currentWaiver": {
                    "out": ["", ""], "in": ["", "", "", ""]}}}
            )

# print(get_waiver_dict('67da30b26a17f44a19c2241a'))


# get_waiver_dict('67da30b26a17f44a19c2241a')
# print(generate_waiver_process(
 #   '67da30b26a17f44a19c2241a', generateEmpty=True))

#final_generate_waiver_results(generateEmpty=False)
#final_generate_waiver_results(generateEmpty=True)

# push_waiver_to_history_and_reset('67da30b26a17f44a19c2241a')  # draft
# push_waiver_to_history_and_reset('67d4dd408786c3e1b4ee172a')  # auction

'''
print(generate_waiver_process(
    '67da30b26a17f44a19c2241a', generateEmpty=False))

print(get_result('67da30b26a17f44a19c2241a', 'Phil Salt',
      'Jitesh Sharma', 'MotaBhai ChotaBhai'))
print(get_result('67da30b26a17f44a19c2241a', 'Phil Salt',
      '', 'MotaBhai ChotaBhai'))
print(get_result('67da30b26a17f44a19c2241a', '',
      'Jitesh Sharma', 'MotaBhai ChotaBhai'))
print(get_result('67da30b26a17f44a19c2241a', 'Phil Salt',
      'Priyansh Arya', 'MotaBhai ChotaBhai'))
'''
