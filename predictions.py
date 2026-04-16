import ssl
import json
import urllib.request
from flask import Blueprint, jsonify, request
from datetime import datetime, timezone, timedelta
from config import db

predictions_bp = Blueprint('predictions', __name__)

IST = timedelta(hours=5, minutes=30)
FEED_URL = "https://ipl-stats-sports-mechanic.s3.ap-south-1.amazonaws.com/ipl/feeds/284-matchschedule.js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ist_today():
    """Return today's date string in IST (YYYY-MM-DD)."""
    return (datetime.now(timezone.utc) + IST).strftime("%Y-%m-%d")


def compute_incoming_streak(prior_predictions):
    """Count consecutive correct predictions from the end of prior history."""
    streak = 0
    for p in reversed(prior_predictions):
        if p.get("isCorrect") is True:
            streak += 1
        else:
            break
    return streak


def compute_score(prior_predictions, predicted_winner, actual_winner):
    """
    Score a single prediction given prior history.
    Returns dict with isCorrect, correctPoints, streakPoints, totalPoints.
    """
    is_correct = predicted_winner == actual_winner
    correct_points = 10 if is_correct else 0

    incoming_streak = compute_incoming_streak(prior_predictions)
    new_streak = (incoming_streak + 1) if is_correct else 0
    streak_points = new_streak if new_streak >= 2 else 0

    return {
        "isCorrect": is_correct,
        "correctPoints": correct_points,
        "streakPoints": streak_points,
        "totalPoints": correct_points + streak_points,
        "streakLength": new_streak,
    }


def update_leaderboard_for_user(database, user_id, is_correct, points_earned, new_streak):
    """
    Incrementally update prediction_leaderboard for a user.
    Entry is created on first save via $setOnInsert.
    """
    database.prediction_leaderboard.update_one(
        {"userId": user_id},
        {
            "$inc": {
                "totalPoints": points_earned,
                "totalPredictions": 1,
                "correctPredictions": 1 if is_correct else 0,
            },
            "$set": {
                "currentStreak": new_streak,
                "lastUpdated": datetime.now(timezone.utc),
            },
            "$max": {
                "maxStreak": new_streak,
            },
            "$setOnInsert": {
                "userId": user_id,
            },
        },
        upsert=True
    )


def process_match_result(database, matchId, winner):
    """
    Score all unscored predictions for a match.
    Skips predictions where isCorrect is already set (idempotency).
    Returns summary dict.
    """
    unscored = list(database.predictions.find({
        "matchId": matchId,
        "isCorrect": None,
    }))

    scored_count = 0
    for pred in unscored:
        user_id = pred["userId"]
        match_number = pred["matchNumber"]

        # Fetch prior scored predictions for this user, ordered by matchNumber
        prior = list(database.predictions.find(
            {
                "userId": user_id,
                "matchNumber": {"$lt": match_number},
                "isCorrect": {"$ne": None},
            },
            {"isCorrect": 1}
        ).sort([("matchNumber", 1)]))

        result = compute_score(prior, pred["predictedWinner"], winner)

        database.predictions.update_one(
            {"_id": pred["_id"]},
            {"$set": {
                "isCorrect": result["isCorrect"],
                "correctPoints": result["correctPoints"],
                "streakPoints": result["streakPoints"],
                "totalPoints": result["totalPoints"],
                "streakLength": result["streakLength"],
            }}
        )

        update_leaderboard_for_user(
            database,
            user_id=user_id,
            is_correct=result["isCorrect"],
            points_earned=result["totalPoints"],
            new_streak=result["streakLength"],
        )

        scored_count += 1

    return {"predictions_scored": scored_count}


def fetch_ipl_feed():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(FEED_URL, context=ctx) as r:
        text = r.read().decode()
    text = text[len('MatchSchedule('):-2]
    data = json.loads(text)
    return {m['MatchID']: m for m in data['Matchsummary']}


def team_code_from_feed(match, team_id):
    tid = str(team_id)
    if str(match['FirstBattingTeamID']) == tid:
        return match['FirstBattingTeamCode']
    if str(match['SecondBattingTeamID']) == tid:
        return match['SecondBattingTeamCode']
    return ''


LOCKED_STATUSES = {"Locked", "Post"}

DUMMY_SCHEDULE = {
    "today": "2026-04-16",
    "tomorrow": "2026-04-17",
    "matches": [
        {"matchId": 2464, "matchNumber": 24, "team1": "MI", "team2": "PBKS",
         "date": "2026-04-16", "scheduledAt": "2026-04-16 19:30 IST",
         "venue": "Wankhede Stadium", "status": "UpComing", "result": "", "winner": ""},
        {"matchId": 2465, "matchNumber": 25, "team1": "GT", "team2": "KKR",
         "date": "2026-04-17", "scheduledAt": "2026-04-17 19:30 IST",
         "venue": "Narendra Modi Stadium", "status": "UpComing", "result": "", "winner": ""},
    ]
}

DUMMY_MY_PREDICTIONS = {
    "predictions": [
        {"matchId": 2464, "matchNumber": 24, "predictedWinner": "MI",
         "submittedAt": "2026-04-16 18:00 IST", "isCorrect": True,
         "correctPoints": 10, "streakPoints": 0, "streakLength": 1, "totalPoints": 10},
        {"matchId": 2463, "matchNumber": 23, "predictedWinner": "RCB",
         "submittedAt": "2026-04-15 18:30 IST", "isCorrect": True,
         "correctPoints": 10, "streakPoints": 2, "streakLength": 2, "totalPoints": 12},
        {"matchId": 2462, "matchNumber": 22, "predictedWinner": "CSK",
         "submittedAt": "2026-04-14 19:00 IST", "isCorrect": False,
         "correctPoints": 0, "streakPoints": 0, "streakLength": 0, "totalPoints": 0},
    ]
}

DUMMY_LEADERBOARD = {
    "leaderboard": [
        {"userId": "abc123", "userName": "Sakshar", "totalPoints": 85, "currentStreak": 3, "maxStreak": 5},
        {"userId": "xyz456", "userName": "Shashank", "totalPoints": 72, "currentStreak": 2, "maxStreak": 4},
        {"userId": "def789", "userName": "Rohit", "totalPoints": 50, "currentStreak": 1, "maxStreak": 3},
    ]
}


def get_leaderboard(database):
    """Return leaderboard sorted by totalPoints desc, with userName joined from users."""
    entries = list(database.prediction_leaderboard.find({}, {"_id": 0}))
    entries.sort(key=lambda x: x.get("totalPoints", 0), reverse=True)

    result = []
    for entry in entries:
        user = database.users.find_one({"_id": entry["userId"]}, {"name": 1})
        user_name = user["name"] if user and "name" in user else entry["userId"]
        result.append({
            "userId": entry["userId"],
            "userName": user_name,
            "totalPoints": entry.get("totalPoints", 0),
            "currentStreak": entry.get("currentStreak", 0),
            "maxStreak": entry.get("maxStreak", 0),
        })
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@predictions_bp.route('/schedule/today', methods=['GET'])
def get_today_schedule():
    if request.args.get('dummy', '').lower() == 'true':
        return jsonify(DUMMY_SCHEDULE), 200

    today_dt = datetime.now(timezone.utc) + IST
    today = today_dt.strftime("%Y-%m-%d")
    tomorrow = (today_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    matches = list(db.schedule.find(
        {"date": {"$in": [today, tomorrow]}},
        {"_id": 0}
    ).sort([("scheduledAt", 1)]))

    for m in matches:
        if m.get("scheduledAt"):
            ist_dt = m["scheduledAt"] + IST
            m["scheduledAt"] = ist_dt.strftime("%Y-%m-%d %H:%M IST")

    return jsonify({
        "today": today,
        "tomorrow": tomorrow,
        "matches": matches
    }), 200


@predictions_bp.route('/cron/sync-matches', methods=['POST'])
def sync_matches():
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # Step 1 — Lock matches whose start time has passed
    lock_result = db.schedule.update_many(
        {"scheduledAt": {"$lte": now_utc}, "status": "UpComing"},
        {"$set": {"status": "Locked"}}
    )
    locked_matches = list(db.schedule.find(
        {"scheduledAt": {"$lte": now_utc}, "status": "Locked"},
        {"_id": 0, "matchId": 1, "matchNumber": 1, "team1": 1, "team2": 1}
    ))

    # Step 2 — Fetch IPL feed and find newly completed matches
    feed = fetch_ipl_feed()
    locked_in_db = list(db.schedule.find({"status": "Locked"}, {"_id": 0}))

    resulted = []
    for match in locked_in_db:
        feed_match = feed.get(match["matchId"])
        if not feed_match:
            continue
        if feed_match.get("MatchStatus") != "Post":
            continue

        winning_id = feed_match.get("WinningTeamID", "")
        winner = team_code_from_feed(feed_match, winning_id) if winning_id else ""
        result_text = feed_match.get("Comments", "")

        db.schedule.update_one(
            {"matchId": match["matchId"]},
            {"$set": {"status": "Post", "winner": winner, "result": result_text}}
        )

        # Step 3 — Score predictions for this match
        scoring_summary = process_match_result(db, match["matchId"], winner)

        resulted.append({
            "matchId": match["matchId"],
            "matchNumber": match["matchNumber"],
            "teams": f"{match['team1']} vs {match['team2']}",
            "winner": winner,
            "predictionsScored": scoring_summary["predictions_scored"],
        })

    return jsonify({
        "locked": [{"matchId": m["matchId"], "matchNumber": m["matchNumber"],
                    "teams": f"{m['team1']} vs {m['team2']}"} for m in locked_matches],
        "resulted": resulted,
        "scored": len(resulted) > 0,
    }), 200


@predictions_bp.route('/predictions/leaderboard', methods=['GET'])
def leaderboard():
    if request.args.get('dummy', '').lower() == 'true':
        return jsonify(DUMMY_LEADERBOARD), 200
    return jsonify({"leaderboard": get_leaderboard(db)}), 200


@predictions_bp.route('/predictions/save', methods=['POST'])
def save_prediction():
    data = request.json or {}
    user_id = data.get("userId")
    match_id = data.get("matchId")
    predicted_winner = data.get("predictedWinner")  # null/empty = clear

    if not user_id or not match_id:
        return jsonify({"error": "userId and matchId are required"}), 400

    match = db.schedule.find_one({"matchId": match_id}, {"_id": 0})
    if not match:
        return jsonify({"error": "Match not found"}), 404

    if match["status"] in LOCKED_STATUSES:
        return jsonify({"error": "Match has started, predictions are locked"}), 403

    # Clear
    if not predicted_winner:
        result = db.predictions.delete_one({"userId": user_id, "matchId": match_id})
        if result.deleted_count == 0:
            return jsonify({"error": "No prediction found to clear"}), 404
        return jsonify({"message": "Prediction cleared"}), 200

    # Insert or update
    db.predictions.update_one(
        {"userId": user_id, "matchId": match_id},
        {"$set": {
            "predictedWinner": predicted_winner,
            "submittedAt": datetime.now(timezone.utc),
        },
        "$setOnInsert": {
            "matchId": match_id,
            "matchNumber": match["matchNumber"],
            "userId": user_id,
            "isCorrect": None,
            "correctPoints": None,
            "streakPoints": None,
            "totalPoints": None,
            "streakLength": None,
        }},
        upsert=True
    )
    return jsonify({"message": "Prediction saved", "matchId": match_id, "predictedWinner": predicted_winner}), 200


@predictions_bp.route('/predictions/my', methods=['GET'])
def my_predictions():
    if request.args.get('dummy', '').lower() == 'true':
        user_id = request.args.get("userId", "dummyUser")
        return jsonify({"userId": user_id, **DUMMY_MY_PREDICTIONS}), 200

    user_id = request.args.get("userId")
    if not user_id:
        return jsonify({"error": "userId is required"}), 400

    preds = list(db.predictions.find(
        {"userId": user_id},
        {"_id": 0}
    ).sort([("matchNumber", -1)]))

    for p in preds:
        if p.get("submittedAt"):
            ist_dt = p["submittedAt"] + IST
            p["submittedAt"] = ist_dt.strftime("%Y-%m-%d %H:%M IST")

    return jsonify({"userId": user_id, "predictions": preds}), 200
