"""Tests for POST /submitWaiverPreferences/<userId>/<teamId>"""
import base64
import json
import pytest
from unittest.mock import patch
from bson import ObjectId
from datetime import datetime, timedelta


FUTURE = (datetime.utcnow() + timedelta(hours=2)).strftime("%B %d, %Y at %I:%M%p")
PAST   = (datetime.utcnow() - timedelta(hours=10)).strftime("%B %d, %Y at %I:%M%p")


def _b64(s):
    return base64.b64encode(s.encode()).decode()


@pytest.fixture(autouse=True)
def no_email():
    with patch('draftapi.notify_waiver_saved'):
        yield


class TestSubmitWaiverPreferences:

    def setup_method(self):
        from main import app
        self.client = app.test_client()

    # ---- helpers ----

    def _seed(self, mock_db, deadline=FUTURE):
        mock_db.global_data.delete_many({})
        mock_db.users.delete_many({})
        mock_db.teams.delete_many({})
        mock_db.players.delete_many({})
        uid = mock_db.users.insert_one({'name': 'Alice'}).inserted_id
        tid = mock_db.teams.insert_one({
            'teamName': 'Alpha', 'leagueId': ObjectId(),
            'batCount': 4, 'ballCount': 3, 'arCount': 2, 'fCount': 2
        }).inserted_id
        mock_db.global_data.insert_one({'nextDraftDeadline': f'{deadline} (PDT)'})
        mock_db.players.insert_one({'player_name': 'Phil Salt',   'player_role': 'BATTER', 'isOverseas': True})
        mock_db.players.insert_one({'player_name': 'Jos Buttler', 'player_role': 'BATTER', 'isOverseas': True})
        return str(uid), str(tid)

    def _post(self, uid, tid, payload):
        return self.client.post(
            f'/submitWaiverPreferences/{uid}/{tid}',
            json=payload,
            content_type='application/json'
        )

    # ---- 200 ----

    def test_valid_submission_returns_200(self, mock_db):
        uid, tid = self._seed(mock_db)
        resp = self._post(uid, tid, {'currentWaiver': {'in': [], 'out': []}})
        assert resp.status_code == 200
        assert 'updated successfully' in json.loads(resp.data)['message']

    # ---- 400: deadline ----

    def test_past_deadline_returns_400(self, mock_db):
        uid, tid = self._seed(mock_db, deadline=PAST)
        resp = self._post(uid, tid, {'currentWaiver': {'in': [], 'out': []}})
        assert resp.status_code == 400
        assert 'nextDraftDeadline' in json.loads(resp.data)['error']

    # ---- 400: mismatched arrays ----

    def test_mismatched_in_out_returns_400(self, mock_db):
        uid, tid = self._seed(mock_db)
        resp = self._post(uid, tid, {'currentWaiver': {
            'in': [_b64('Phil Salt')], 'out': []
        }})
        assert resp.status_code == 400
        assert 'same number' in json.loads(resp.data)['error']

    # ---- 400: single squad rule violation ----

    def test_single_pair_squad_violation_returns_400(self, mock_db):
        uid, tid = self._seed(mock_db)
        # batCount=2 is minimum; dropping a batter violates the rule
        mock_db.teams.update_one({'_id': ObjectId(tid)}, {'$set': {'batCount': 2}})
        mock_db.players.insert_one({'player_name': 'Rashid Khan', 'player_role': 'BOWLER', 'isOverseas': True})
        resp = self._post(uid, tid, {'currentWaiver': {
            'in':  [_b64('Rashid Khan')],
            'out': [_b64('Phil Salt')]
        }})
        assert resp.status_code == 400
        errors = json.loads(resp.data)['errors']
        assert len(errors) == 1
        assert 'batters' in errors[0]

    # ---- 400: multiple pair errors all returned ----

    def test_multiple_pair_violations_all_returned(self, mock_db):
        uid, tid = self._seed(mock_db)
        # Both batCount and ballCount at minimum; both pairs will violate
        mock_db.teams.update_one({'_id': ObjectId(tid)}, {'$set': {'batCount': 2, 'ballCount': 2}})
        mock_db.players.insert_one({'player_name': 'Rashid Khan', 'player_role': 'BOWLER', 'isOverseas': True})
        mock_db.players.insert_one({'player_name': 'Trent Boult', 'player_role': 'BOWLER', 'isOverseas': True})
        resp = self._post(uid, tid, {'currentWaiver': {
            'in':  [_b64('Rashid Khan'),  _b64('Trent Boult')],
            'out': [_b64('Phil Salt'),    _b64('Jos Buttler')]
        }})
        assert resp.status_code == 400
        errors = json.loads(resp.data)['errors']
        assert len(errors) == 2
