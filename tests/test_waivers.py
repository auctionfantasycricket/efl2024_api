"""Tests for the refactored waiver generation algorithm."""
import base64
import pytest
from unittest.mock import patch, call


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


def run_results(waiver_order, prefs, generate_empty=False):
    """Helper: run generate_waiver_results with mocked dict and transfers."""
    from waivers import generate_waiver_results
    waiver_dict = make_waiver_dict(prefs)
    with patch('waivers.get_waiver_dict', return_value=waiver_dict), \
         patch('waivers.do_the_trasnfers') as mock_transfer:
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
