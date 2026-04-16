"""
Fetch IPL 2026 match schedule from the S3 feed and populate db.schedule.

Run: python3 scripts/populate_schedule.py
"""
import ssl
import json
import urllib.request
from datetime import datetime, timedelta
from pymongo import MongoClient, UpdateOne

IST = timedelta(hours=5, minutes=30)

FEED_URL = "https://ipl-stats-sports-mechanic.s3.ap-south-1.amazonaws.com/ipl/feeds/284-matchschedule.js"
MONGO_URI = "mongodb+srv://efladmin:god_is_watching@cluster0.eezohvz.mongodb.net/?retryWrites=true&w=majority"


def fetch_schedule():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(FEED_URL, context=ctx) as r:
        text = r.read().decode()
    # Strip JSONP wrapper: MatchSchedule({...});
    text = text[len('MatchSchedule('):-2]
    return json.loads(text)['Matchsummary']


def team_code(match, team_id):
    """Return short code for a given team ID using FirstBatting/SecondBatting fields."""
    tid = str(team_id)
    if str(match['FirstBattingTeamID']) == tid:
        return match['FirstBattingTeamCode']
    if str(match['SecondBattingTeamID']) == tid:
        return match['SecondBattingTeamCode']
    return ''


def parse_match(m):
    home_id = m.get('HomeTeamID', '')
    away_id = m.get('AwayTeamID', '')
    winning_id = m.get('WinningTeamID', '')

    home_code = team_code(m, home_id) if home_id else ''
    away_code = team_code(m, away_id) if away_id else ''
    winner_code = team_code(m, winning_id) if winning_id else ''

    date_str = m['MatchDate']   # "2026-04-16"
    time_str = m['MatchTime']   # "19:30" IST
    ist_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    utc_dt = ist_dt - IST

    return {
        'matchId': m['MatchID'],
        'matchNumber': m['MatchRow'],
        'team1': home_code,
        'team2': away_code,
        'date': date_str,           # "2026-04-16" IST date (for today-query)
        'scheduledAt': utc_dt,      # UTC datetime (for lock logic)
        'venue': m['GroundName'],
        'status': m['MatchStatus'],   # "UpComing" | "Locked" | "Post"
        'result': m.get('Comments', ''),
        'winner': winner_code,
    }


def main():
    raw_matches = fetch_schedule()
    print(f"Fetched {len(raw_matches)} matches from feed")

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000, tlsAllowInvalidCertificates=True)
    db = client['afc2026']

    upcoming = [m for m in raw_matches if m['MatchStatus'] == 'UpComing']
    print(f"Upcoming matches: {len(upcoming)}")

    ops = []
    for m in upcoming:
        doc = parse_match(m)
        ops.append(UpdateOne(
            {'matchId': doc['matchId']},
            {'$set': doc},
            upsert=True
        ))

    result = db.schedule.bulk_write(ops)
    print(f"Upserted: {result.upserted_count}, Modified: {result.modified_count}")

    # Preview first 5
    print("\nFirst 5 matches in db.schedule:")
    for doc in db.schedule.find({}, {'_id': 0}).sort('matchNumber', 1).limit(5):
        print(f"  #{doc['matchNumber']:>2} {doc['date']} UTC={doc['scheduledAt']}  {doc['team1']} vs {doc['team2']}  [{doc['status']}]")

    client.close()


if __name__ == '__main__':
    main()
