"""
Shared utility functions for the EFL2024 API.

Previously these functions were duplicated across main.py, draftapi.py,
add_drop.py, transfers.py, and waivers.py. They now live here.
"""
from config import db
from bson import ObjectId


# ---------------------------------------------------------------------------
# Role count helpers
# ---------------------------------------------------------------------------

def update_role_counts(owner_items, role, delta):
    """
    Adjust batCount / ballCount / arCount on owner_items by delta (+1 or -1).
    Role string is normalised to uppercase before matching.
    Returns True if the role was recognised, False otherwise.
    """
    role = role.upper()
    if role == "BATTER":
        owner_items["batCount"] += delta
    elif role == "BOWLER":
        owner_items["ballCount"] += delta
    elif role == "ALL_ROUNDER":
        owner_items["arCount"] += delta
    else:
        return False
    return True


# ---------------------------------------------------------------------------
# Waiver history helper  (identical logic in transfers.py and waivers.py)
# ---------------------------------------------------------------------------

def push_waiver_to_history_and_reset(leagueID):
    """
    For every team in leagueID:
      - push their currentWaiver into waiverHistory
      - reset currentWaiver to empty slots
    """
    teams = db.teams.find({"leagueId": ObjectId(leagueID)})

    for team in teams:
        current_waiver = team.get("currentWaiver", None)

        if current_waiver:
            db.teams.update_one(
                {"_id": team["_id"]},
                {
                    "$push": {"waiverHistory": current_waiver},
                    "$set": {"currentWaiver": {"out": ["", ""], "in": ["", "", "", ""]}}
                }
            )
        else:
            db.teams.update_one(
                {"_id": team["_id"]},
                {"$set": {"currentWaiver": {"out": ["", ""], "in": ["", "", "", ""]}}}
            )


# ---------------------------------------------------------------------------
# Global data helper  (identical in main.py and liveupdates.py)
# ---------------------------------------------------------------------------

def get_global_data(attribute_name):
    """Fetch a single attribute from the global_data collection."""
    global_collection = db['global_data']
    document = global_collection.find_one({})
    return document[attribute_name]


# ---------------------------------------------------------------------------
# Player drop core  (shared across add_drop.py, draftapi.py, transfers.py)
# ---------------------------------------------------------------------------

def _drop_player_core(player_data, player_collection, id_filter, owner,
                      extra_player_fields=None):
    """
    Shared drop steps common to all three drop functions:
      - mark the player as unsold-dropped in the player collection
      - append a transfer history entry to the owner dict
      - decrement totalCount on the owner dict

    extra_player_fields: optional dict merged into the $set update on the player
      (e.g. {"points": 0} for the draftapi drop that also resets points).

    Each caller is responsible for role-count and purse adjustments
    (they vary between draft and auction formats).

    Returns the player's boughtFor value so callers can use it for
    purse refunds.
    """
    from datetime import datetime

    player_name = player_data.get("player_name", "")
    points = player_data.get("points", 0)
    bought_for = player_data.get("boughtFor", 0)
    transfer_date = datetime.now().strftime("%d %B, %Y")

    set_fields = {"ownerTeam": "", "status": "unsold-dropped"}
    if extra_player_fields:
        set_fields.update(extra_player_fields)
    player_collection.update_one(id_filter, {"$set": set_fields})

    entry = {"player_name": player_name, "points": points,
             "transfer_date": transfer_date}
    if "transferHistory" not in owner:
        owner["transferHistory"] = [entry]
    else:
        owner["transferHistory"].append(entry)

    owner["totalCount"] -= 1

    return bought_for


# ---------------------------------------------------------------------------
# Base64 decode array  (defined in draftapi.py, re-implemented in waivers.py
# and transfers.py)
# ---------------------------------------------------------------------------

def de_arr(arr):
    """Base64-decode every element in arr and return a list of plain strings."""
    import base64
    return [base64.b64decode(a).decode('utf-8') for a in arr]


# ---------------------------------------------------------------------------
# Squad composition validation  (shared by draftapi.py and waivers.py)
# ---------------------------------------------------------------------------

def violated_rules(counts):
    """Return a list of violated squad composition rules for the given counts."""
    rules = []
    if counts['batCount'] < 2:
        rules.append('batters (min 2)')
    if counts['ballCount'] < 2:
        rules.append('bowlers (min 2)')
    if counts['arCount'] < 2:
        rules.append('all-rounders (min 2)')
    if counts['fCount'] < 1:
        rules.append('overseas (min 1)')
    if counts['fCount'] > 3:
        rules.append('overseas (max 3)')
    return rules
