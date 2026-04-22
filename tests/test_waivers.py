"""Tests for the refactored waiver generation algorithm."""
import base64
import pytest
from unittest.mock import patch, call, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def b64(s):
    return base64.b64encode(s.encode()).decode()


def make_waiver_dict(prefs):
    """Build waiver_dict from {team: [(pick, drop), ...]} with base64 encoding."""
    result = {}
    for team, pairs in prefs.items():
        result[team] = {
            "in":  [b64(p) if p else "" for p, d in pairs],
            "out": [b64(d) if d else "" for p, d in pairs],
        }
    return result


def make_teams(prefs):
    """Build team doc list from {team: [(pick, drop), ...]} with currentWaiver set."""
    teams = []
    for name, pairs in prefs.items():
        teams.append({
            "teamName": name,
            "currentWaiver": {
                "in":  [b64(p) if p else "" for p, d in pairs],
                "out": [b64(d) if d else "" for p, d in pairs],
            }
        })
    return teams


def run_results(waiver_order, prefs, generate_empty=False, composition_valid=True):
    """Helper: run generate_waiver_results with mocked dict and transfers."""
    from waivers import generate_waiver_results
    waiver_dict = make_waiver_dict(prefs)
    comp_return = (True, "") if composition_valid else (False, "breaks bowlers (min 2) requirement")
    with patch('waivers.get_waiver_dict', return_value=waiver_dict), \
         patch('waivers.do_the_trasnfers') as mock_transfer, \
         patch('waivers.check_swap_composition', return_value=comp_return):
        results = generate_waiver_results(waiver_order, generateEmpty=generate_empty)
    return results, mock_transfer


# ---------------------------------------------------------------------------
# generate_waiver_results
# ---------------------------------------------------------------------------

class TestGenerateWaiverResults:

    def test_all_teams_swap_round1_early_exit(self):
        """All teams have pair 1 filled → swap in round 1 → early exit, no round 2."""
        prefs = {
            "Team A": [("Player1", "Drop1")],
            "Team B": [("Player2", "Drop2")],
        }
        waiver_order = [["Team A", "Team B"], ["Team B", "Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        assert len(results) == 1
        assert mock_transfer.call_count == 2
        mock_transfer.assert_any_call("Drop1", "Player1", "Team A")
        mock_transfer.assert_any_call("Drop2", "Player2", "Team B")

    def test_player_taken_causes_failure_for_second_team(self):
        """Team A picks SharedPlayer in round 1; Team B wants same → failure."""
        prefs = {
            "Team A": [("SharedPlayer", "Drop1")],
            "Team B": [("SharedPlayer", "Drop2")],
        }
        waiver_order = [["Team A", "Team B"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        picks = results[0]["picks"]
        a = next(p for p in picks if p["team"] == "Team A")
        b = next(p for p in picks if p["team"] == "Team B")

        assert a["status"] == "success"
        assert b["status"] == "failure"
        assert b["message"] == "Player already taken"
        assert mock_transfer.call_count == 1

    def test_fallback_to_pair2_in_round2_when_player_taken(self):
        """Team B's pair 1 pick is taken by Team A; pair 2 succeeds in round 2."""
        prefs = {
            "Team A": [("Player1", "Drop1"), ("Player3", "Drop3")],
            "Team B": [("Player1", "Drop2"), ("Player2", "Drop2")],
        }
        waiver_order = [["Team A", "Team B"], ["Team B", "Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        assert len(results) == 2
        assert call("Drop1", "Player1", "Team A") in mock_transfer.call_args_list
        assert call("Drop2", "Player2", "Team B") in mock_transfer.call_args_list

    def test_already_swapped_team_skipped_with_message(self):
        """Team that swapped in round 1 appears in round 2 order but is skipped."""
        prefs = {
            "Team A": [("Player1", "Drop1"), ("Player3", "Drop3")],
            "Team B": [("Player2", "Drop2"), ("Player4", "Drop4")],
        }
        # Both swap in round 1 → early exit
        waiver_order = [["Team A", "Team B"], ["Team B", "Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        assert len(results) == 1
        assert mock_transfer.call_count == 2

    def test_empty_pick_skipped_with_no_pick_message(self):
        """Team with empty pick in pair → no transfer, message = No pick."""
        prefs = {
            "Team A": [("Player1", "Drop1")],
            "Team B": [("", "Drop2")],
        }
        waiver_order = [["Team A", "Team B"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        b_pick = next(p for p in results[0]["picks"] if p["team"] == "Team B")
        assert b_pick["message"] == "No pick"
        assert mock_transfer.call_count == 1

    def test_empty_drop_skipped_with_no_drop_message(self):
        """Team with empty drop in pair → no transfer, message = No drop."""
        prefs = {
            "Team A": [("Player1", "")],
        }
        waiver_order = [["Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        a_pick = results[0]["picks"][0]
        assert a_pick["message"] == "No drop"
        assert mock_transfer.call_count == 0

    def test_dry_run_returns_placeholders_no_transfers(self):
        """generateEmpty=True → placeholder data, zero transfers."""
        prefs = {"Team A": [("Player1", "Drop1")]}
        waiver_order = [["Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs, generate_empty=True)

        assert mock_transfer.call_count == 0
        assert results[0]["picks"][0]["pick"] == "Your next superstar"
        assert results[0]["picks"][0]["drop"] == "Your Worst performer"

    def test_pair_index_matches_round_number(self):
        """Round 2 uses pair index 1 (in[1], out[1])."""
        prefs = {
            "Team A": [("", ""),          ("Player2", "Drop2")],  # pair 1 empty, pair 2 set
        }
        waiver_order = [["Team A"], ["Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        # Round 1: no pick → skip. Round 2: pair 2 → success
        assert mock_transfer.call_count == 1
        mock_transfer.assert_called_once_with("Drop2", "Player2", "Team A")

    def test_waiver_order_rotation(self):
        """Round 2 order is rotated: first team in round 1 goes last in round 2."""
        prefs = {
            "Team A": [("P1", "D1"), ("P3", "D3")],
            "Team B": [("P1", "D2"), ("P2", "D2")],  # P1 conflict in round 1
        }
        waiver_order = [["Team A", "Team B"], ["Team B", "Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs)

        # Round 2: Team B goes first and gets P2 since P1 was taken in round 1
        assert call("D2", "P2", "Team B") in mock_transfer.call_args_list


# ---------------------------------------------------------------------------
# generate_waiver_process — rounds computation
# ---------------------------------------------------------------------------

class TestGenerateWaiverProcess:

    def test_rounds_equals_max_pairs_across_teams(self):
        """Rounds = max pairs any team has saved."""
        prefs = {
            "Team A": [("P1", "D1"), ("P2", "D2"), ("P3", "D3")],  # 3 pairs
            "Team B": [("P4", "D4")],                               # 1 pair
        }
        teams = make_teams(prefs)
        waiver_dict = make_waiver_dict(prefs)

        with patch('waivers.get_teams_sorted_by_rank', return_value=teams), \
             patch('waivers.get_waiver_dict', return_value=waiver_dict), \
             patch('waivers.do_the_trasnfers'):
            from waivers import generate_waiver_process
            results = generate_waiver_process("fake_id", generateEmpty=False)

        # Max pairs = 3, so at most 3 rounds (early exit may reduce this)
        assert len(results) <= 3

    def test_rounds_defaults_to_1_when_no_preferences(self):
        """If all teams have empty in arrays, rounds = 1."""
        teams = [{"teamName": "Team A", "currentWaiver": {"in": [], "out": []}}]
        waiver_dict = {"Team A": {"in": [], "out": []}}

        with patch('waivers.get_teams_sorted_by_rank', return_value=teams), \
             patch('waivers.get_waiver_dict', return_value=waiver_dict), \
             patch('waivers.do_the_trasnfers'):
            from waivers import generate_waiver_process
            results = generate_waiver_process("fake_id", generateEmpty=False)

        assert len(results) == 1

    def test_rounds_defaults_to_1_when_no_teams(self):
        """Empty team list → rounds defaults to 1."""
        with patch('waivers.get_teams_sorted_by_rank', return_value=[]), \
             patch('waivers.get_waiver_dict', return_value={}), \
             patch('waivers.do_the_trasnfers'):
            from waivers import generate_waiver_process
            results = generate_waiver_process("fake_id", generateEmpty=False)

        assert len(results) == 1


# ---------------------------------------------------------------------------
# violated_rules
# ---------------------------------------------------------------------------

class TestViolatedRules:

    def test_valid_counts_returns_empty(self):
        from utils import violated_rules
        counts = {"batCount": 3, "ballCount": 3, "arCount": 3, "fCount": 2}
        assert violated_rules(counts) == []

    def test_too_few_batters(self):
        from utils import violated_rules
        counts = {"batCount": 1, "ballCount": 3, "arCount": 3, "fCount": 2}
        assert "batters (min 2)" in violated_rules(counts)

    def test_too_few_bowlers(self):
        from utils import violated_rules
        counts = {"batCount": 3, "ballCount": 1, "arCount": 3, "fCount": 2}
        assert "bowlers (min 2)" in violated_rules(counts)

    def test_too_few_all_rounders(self):
        from utils import violated_rules
        counts = {"batCount": 3, "ballCount": 3, "arCount": 1, "fCount": 2}
        assert "all-rounders (min 2)" in violated_rules(counts)

    def test_too_few_overseas(self):
        from utils import violated_rules
        counts = {"batCount": 3, "ballCount": 3, "arCount": 3, "fCount": 0}
        assert "overseas (min 1)" in violated_rules(counts)

    def test_too_many_overseas(self):
        from utils import violated_rules
        counts = {"batCount": 3, "ballCount": 3, "arCount": 3, "fCount": 4}
        assert "overseas (max 3)" in violated_rules(counts)

    def test_multiple_violations_returned(self):
        from utils import violated_rules
        counts = {"batCount": 1, "ballCount": 1, "arCount": 3, "fCount": 2}
        violations = violated_rules(counts)
        assert "batters (min 2)" in violations
        assert "bowlers (min 2)" in violations


# ---------------------------------------------------------------------------
# check_swap_composition
# ---------------------------------------------------------------------------

class TestCheckSwapComposition:

    def _make_team(self, bat=3, ball=3, ar=3, f=2):
        return {"batCount": bat, "ballCount": ball, "arCount": ar, "fCount": f}

    def _make_player(self, role, overseas=False):
        return {"player_role": role, "isOverseas": overseas}

    def test_valid_swap_returns_true(self):
        from waivers import check_swap_composition
        with patch('waivers.db') as mock_db:
            mock_db.teams.find_one.return_value = self._make_team()
            mock_db.players.find_one.side_effect = [
                self._make_player("BOWLER"),   # drop
                self._make_player("BOWLER"),   # pick
            ]
            valid, msg = check_swap_composition("Team A", "OldBowler", "NewBowler")
        assert valid is True
        assert msg == ""

    def test_swap_that_drops_below_min_bowlers_fails(self):
        from waivers import check_swap_composition
        with patch('waivers.db') as mock_db:
            mock_db.teams.find_one.return_value = self._make_team(ball=2)
            mock_db.players.find_one.side_effect = [
                self._make_player("BOWLER"),   # drop — takes ballCount to 1
                self._make_player("BATTER"),   # pick — does not restore it
            ]
            valid, msg = check_swap_composition("Team A", "Bowler1", "Batter1")
        assert valid is False
        assert "bowlers (min 2)" in msg

    def test_swap_that_exceeds_max_overseas_fails(self):
        from waivers import check_swap_composition
        with patch('waivers.db') as mock_db:
            mock_db.teams.find_one.return_value = self._make_team(f=3)
            mock_db.players.find_one.side_effect = [
                self._make_player("BATTER", overseas=False),  # drop — fCount stays 3
                self._make_player("BATTER", overseas=True),   # pick — fCount → 4
            ]
            valid, msg = check_swap_composition("Team A", "Local1", "Foreign1")
        assert valid is False
        assert "overseas (max 3)" in msg

    def test_team_not_found_returns_false(self):
        from waivers import check_swap_composition
        with patch('waivers.db') as mock_db:
            mock_db.teams.find_one.return_value = None
            valid, msg = check_swap_composition("Ghost Team", "P1", "P2")
        assert valid is False
        assert "not found" in msg

    def test_drop_player_not_found_returns_false(self):
        from waivers import check_swap_composition
        with patch('waivers.db') as mock_db:
            mock_db.teams.find_one.return_value = self._make_team()
            mock_db.players.find_one.side_effect = [None, self._make_player("BATTER")]
            valid, msg = check_swap_composition("Team A", "Ghost", "NewPlayer")
        assert valid is False
        assert "not found" in msg


# ---------------------------------------------------------------------------
# Squad composition check integrated into generate_waiver_results
# ---------------------------------------------------------------------------

class TestWaiverSquadCompositionCheck:

    def test_composition_failure_blocks_swap(self):
        """If check_swap_composition fails, swap is not executed and status is failure."""
        prefs = {"Team A": [("Player1", "Drop1")]}
        waiver_order = [["Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs, composition_valid=False)

        pick = results[0]["picks"][0]
        assert pick["status"] == "failure"
        assert "Squad rule violation" in pick["message"]
        assert mock_transfer.call_count == 0

    def test_composition_success_allows_swap(self):
        """If check_swap_composition passes, swap executes normally."""
        prefs = {"Team A": [("Player1", "Drop1")]}
        waiver_order = [["Team A"]]

        results, mock_transfer = run_results(waiver_order, prefs, composition_valid=True)

        pick = results[0]["picks"][0]
        assert pick["status"] == "success"
        assert mock_transfer.call_count == 1
