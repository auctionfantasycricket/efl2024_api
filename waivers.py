from bson.objectid import ObjectId
from bson import ObjectId
from config import db, DRAFT_LEAGUE_ID
from utils import push_waiver_to_history_and_reset
import base64
import binascii
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
import add_drop


waivers_bp = Blueprint('waivers', __name__)


def get_teams_sorted_by_rank(league_id):
    """Fetch teams in the league sorted by rank descending (lowest rank first)."""
    teams = list(db.teams.find(
        {"leagueId": ObjectId(league_id)}).sort("rank", -1))
    return teams


def generate_waiver_order(teams, rounds):
    """Generate the rotating waiver order for the given number of rounds."""
    order = []
    for i in range(rounds):
        rotated_teams = teams[i:] + teams[:i]
        order.append([team["teamName"] for team in rotated_teams])
    return order


def get_waiver_dict(leagueId):
    waiver_dict = {}
    teams = db.teams.find({"leagueId": ObjectId(leagueId)}, {
                          "teamName": 1, "currentWaiver": 1, "_id": 0})
    for team in teams:
        team_name = team["teamName"]
        current_waiver = team.get("currentWaiver", {"out": [], "in": []})
        waiver_dict[team_name] = current_waiver
    return waiver_dict


def do_the_trasnfers(nextdrop, nextpick, team):
    add_drop.draftplayer(nextpick, team, str(DRAFT_LEAGUE_ID))
    add_drop.drop_draft_player(nextdrop, str(DRAFT_LEAGUE_ID))


def generate_waiver_process(league_id, generateEmpty=True):
    """Main function to generate waiver process based on league ID."""
    teams = get_teams_sorted_by_rank(league_id)

    # Rounds = max number of pairs any team has saved
    rounds = max(
        (len(team.get("currentWaiver", {}).get("in", [])) for team in teams),
        default=1
    )
    if rounds == 0:
        rounds = 1

    waiver_order = generate_waiver_order(teams, rounds)
    print(waiver_order)
    results = generate_waiver_results(waiver_order, generateEmpty)
    return results


def generate_waiver_results(waiver_order, generateEmpty=True):
    waiver_results = []
    waiver_dict = get_waiver_dict(str(DRAFT_LEAGUE_ID))
    swapped_teams = set()   # teams that completed their 1 swap
    picked_players = set()  # players already picked this run

    for round_num, order in enumerate(waiver_order, start=1):
        round_result = {
            "round": round_num,
            "waiverOrder": order,
            "picks": []
        }

        for team in order:
            if not generateEmpty:
                # Skip teams that already had a successful swap
                if team in swapped_teams:
                    round_result["picks"].append({
                        "team": team,
                        "drop": "",
                        "pick": "",
                        "status": "",
                        "message": "Already swapped"
                    })
                    continue

                pair_index = round_num - 1
                team_waiver = waiver_dict.get(team, {"in": [], "out": []})
                in_arr = team_waiver.get("in", [])
                out_arr = team_waiver.get("out", [])

                raw_pick = in_arr[pair_index] if pair_index < len(in_arr) else ""
                raw_drop = out_arr[pair_index] if pair_index < len(out_arr) else ""

                try:
                    nextpick = base64.b64decode(raw_pick).decode('utf-8') if raw_pick else ""
                    nextdrop = base64.b64decode(raw_drop).decode('utf-8') if raw_drop else ""
                except binascii.Error:
                    print('decode error', team, raw_pick, raw_drop)
                    nextpick = raw_pick
                    nextdrop = raw_drop

                if not nextpick:
                    status, message = "", "No pick"
                elif not nextdrop:
                    status, message = "", "No drop"
                elif nextpick in picked_players:
                    status, message = "failure", "Player already taken"
                else:
                    do_the_trasnfers(nextdrop, nextpick, team)
                    status, message = "success", "Swap done"
                    swapped_teams.add(team)
                    picked_players.add(nextpick)

                round_result["picks"].append({
                    "team": team,
                    "drop": nextdrop,
                    "pick": nextpick,
                    "status": status,
                    "message": message
                })
            else:
                round_result["picks"].append({
                    "team": team,
                    "drop": "Your Worst performer",
                    "pick": "Your next superstar",
                    "status": "",
                    "message": ""
                })

        waiver_results.append(round_result)

        # Early exit once every team has swapped
        if not generateEmpty and len(swapped_teams) >= len(waiver_dict):
            break

    return waiver_results


def _advance_draft_deadline():
    """Bump nextDraftDeadline forward by 7 days, preserving the time-of-day."""
    global_data = db.global_data.find_one({}, {"nextDraftDeadline": 1})
    if not global_data or "nextDraftDeadline" not in global_data:
        print("nextDraftDeadline not found in global_data, skipping advance")
        return
    current = global_data["nextDraftDeadline"]
    # Format: "April 14, 2026 at 9:00PM (PST)"
    try:
        dt = datetime.strptime(current.split(" (")[0], "%B %d, %Y at %I:%M%p")
        next_dt = dt + timedelta(weeks=1)
        suffix = current.split(" (")[1].rstrip(")")  # e.g. "PST"
        new_deadline = next_dt.strftime("%B %-d, %Y at %-I:%M%p") + f" ({suffix})"
        db.global_data.update_one({}, {"$set": {"nextDraftDeadline": new_deadline}})
        print(f"nextDraftDeadline advanced: {current} → {new_deadline}")
    except Exception as e:
        print(f"Failed to advance nextDraftDeadline: {e}")


@waivers_bp.route('/final_generate_waiver_results', methods=['POST'])
def final_generate_waiver_results():
    generateEmpty = request.args.get('generateEmpty', 'true').lower() == 'true'
    waiverResults = generate_waiver_process(
        str(DRAFT_LEAGUE_ID), generateEmpty)
    result = db.leagues.update_one(
        {"_id": DRAFT_LEAGUE_ID},
        {"$set": {"waiverResults": waiverResults}},
        upsert=True
    )
    if not generateEmpty:
        push_waiver_to_history_and_reset(str(DRAFT_LEAGUE_ID))
        _advance_draft_deadline()

    print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")

    if result.matched_count == 0:
        print("No matching league found. A new document may have been created.")
    elif result.modified_count > 0:
        print(f"Waiver results successfully updated for league ID: {DRAFT_LEAGUE_ID}")
    else:
        print("Waiver results were already up to date. No changes made.")

    return jsonify({"message": "Waiver results generated", "waiverResults": waiverResults}), 200
