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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@predictions_bp.route('/schedule/today', methods=['GET'])
def get_today_schedule():
    today = ist_today()
    matches = list(db.schedule.find(
        {"date": today},
        {"_id": 0}
    ).sort("scheduledAt", 1))
    for m in matches:
        if m.get("scheduledAt"):
            ist_dt = m["scheduledAt"] + IST
            m["scheduledAt"] = ist_dt.strftime("%Y-%m-%d %H:%M IST")
    return jsonify({"date": today, "matches": matches}), 200


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
