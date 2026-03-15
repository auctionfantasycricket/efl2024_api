"""
RED → GREEN tests for leagueplayers normalization.

Phase 1 (RED): these tests fail against current code because:
  - create_league() copies 8 static fields into leagueplayers (should only write playerId)
  - /get_data does a raw find() (should do $lookup to flatten static fields back)

Phase 2 (GREEN): pass after implementing playerId + $lookup changes.

NOTE: mongomock has partial $lookup support. The $lookup tests are marked with
a comment noting they should also be validated against real Atlas afc2026.
"""
import pytest
import json
from bson import ObjectId


STATIC_FIELDS = [
    "player_name", "player_role", "ipl_team_name",
    "isOverseas", "ipl_salary", "rank", "tier", "afc_base_salary"
]

DYNAMIC_FIELDS = ["status", "leagueId", "playerId"]


def _seed_player(mock_db):
    player = {
        "_id": ObjectId(),
        "player_name": "Virat Kohli",
        "player_role": "BATTER",
        "ipl_team_name": "RCB",
        "isOverseas": False,
        "ipl_salary": 15.0,
        "rank": 1,
        "tier": 1,
        "afc_base_salary": 200,
        "type": "retained"
    }
    mock_db.players.insert_one(player)
    return player


def _create_league(client, email="admin@test.com"):
    return client.post("/create_league", json={
        "useremail": email,
        "league_name": "Test League",
        "league_type": "draft"
    })


# ---------------------------------------------------------------------------
# create_league() schema tests
# ---------------------------------------------------------------------------

class TestCreateLeagueLeagueplayersSchema:

    def setup_method(self):
        from main import app
        self.client = app.test_client()

    def test_leagueplayer_has_playerId(self, mock_db):
        player = _seed_player(mock_db)
        _create_league(self.client)
        lp = mock_db.leagueplayers.find_one({})
        assert lp is not None
        assert "playerId" in lp
        assert lp["playerId"] == player["_id"]

    def test_leagueplayer_has_no_static_fields(self, mock_db):
        _seed_player(mock_db)
        _create_league(self.client)
        lp = mock_db.leagueplayers.find_one({})
        assert lp is not None
        for field in STATIC_FIELDS:
            assert field not in lp, f"Expected '{field}' to be absent from leagueplayers"

    def test_leagueplayer_has_dynamic_fields(self, mock_db):
        _seed_player(mock_db)
        _create_league(self.client)
        lp = mock_db.leagueplayers.find_one({})
        assert lp is not None
        assert lp["status"] == "unsold"
        assert "leagueId" in lp
        assert "playerId" in lp

    def test_leagueplayer_count_matches_players(self, mock_db):
        _seed_player(mock_db)
        resp = _create_league(self.client)
        league_id = ObjectId(resp.get_json()["leagueId"])
        expected = mock_db.players.count_documents({})
        assert mock_db.leagueplayers.count_documents({"leagueId": league_id}) == expected


# ---------------------------------------------------------------------------
# /get_data $lookup tests
# ---------------------------------------------------------------------------

class TestGetDataLeagueplayersLookup:
    """
    Seeds a leagueplayer with only playerId + dynamic fields (new schema),
    then calls GET /get_data?collectionName=leagueplayers and asserts all
    8 static fields are present in the response via $lookup.

    NOTE: mongomock $lookup support is partial — validate against real Atlas too.
    """

    def setup_method(self):
        from main import app
        self.client = app.test_client()

    def _seed(self, mock_db):
        player = _seed_player(mock_db)
        league_id = ObjectId()
        lp = {
            "playerId": player["_id"],
            "status": "unsold",
            "leagueId": league_id,
        }
        mock_db.leagueplayers.insert_one(lp)
        return player, league_id

    def test_response_includes_all_static_fields(self, mock_db):
        player, league_id = self._seed(mock_db)
        resp = self.client.get(f"/get_data?collectionName=leagueplayers&leagueId={league_id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 1
        doc = data[0]
        for field in STATIC_FIELDS:
            assert field in doc, f"Expected '{field}' in /get_data response"

    def test_response_static_values_correct(self, mock_db):
        player, league_id = self._seed(mock_db)
        resp = self.client.get(f"/get_data?collectionName=leagueplayers&leagueId={league_id}")
        data = json.loads(resp.data)
        doc = data[0]
        assert doc["player_name"] == "Virat Kohli"
        assert doc["player_role"] == "BATTER"
        assert doc["tier"] == 1

    def test_response_includes_dynamic_fields(self, mock_db):
        player, league_id = self._seed(mock_db)
        resp = self.client.get(f"/get_data?collectionName=leagueplayers&leagueId={league_id}")
        data = json.loads(resp.data)
        doc = data[0]
        assert doc["status"] == "unsold"

    def test_other_collections_unaffected(self, mock_db):
        # /get_data for non-leagueplayers collections still works normally
        resp = self.client.get("/get_data?collectionName=players")
        assert resp.status_code == 200
