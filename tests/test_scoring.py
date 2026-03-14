"""Baseline tests for pure scoring functions in main.py."""
import pytest
from main import (
    calculate_batting_points,
    calculate_bowling_points,
    calculate_fielding_points,
    calculate_total_points,
)


# ---------------------------------------------------------------------------
# calculate_batting_points
# ---------------------------------------------------------------------------

class TestCalculateBattingPoints:

    def _stats(self, runs=0, fours=0, sixes=0, sr=100.0, isOut=False, balls=10):
        return {'runs': runs, 'fours': fours, 'sixes': sixes,
                'sr': sr, 'isOut': isOut, 'balls': balls}

    def test_basic_runs_fours_sixes(self):
        stats = self._stats(runs=20, fours=2, sixes=1)
        # 20 runs + 2 fours (1pt each) + 2*1 six (2pt each) = 24
        assert calculate_batting_points(stats) == 24

    def test_milestone_30(self):
        stats = self._stats(runs=30, balls=15, sr=200.0)
        # 30 + 4 (milestone) + 6 (sr>170) = 40
        assert calculate_batting_points(stats) == 40

    def test_milestone_50(self):
        stats = self._stats(runs=50, balls=30, sr=166.0)
        # 50 + 8 (milestone) + 4 (sr 150-170) = 62
        assert calculate_batting_points(stats) == 62

    def test_milestone_100(self):
        stats = self._stats(runs=100, balls=60, sr=166.0)
        # 100 + 16 (century) + 4 (sr 150-170) = 120
        assert calculate_batting_points(stats) == 120

    def test_duck_penalty(self):
        stats = self._stats(runs=0, isOut=True, balls=3)
        # 0 runs, out, balls < 10 so no sr bonus/penalty, duck = -2
        assert calculate_batting_points(stats) == -2

    def test_not_out_zero_no_penalty(self):
        stats = self._stats(runs=0, isOut=False, balls=3)
        assert calculate_batting_points(stats) == 0

    def test_strike_rate_above_170(self):
        stats = self._stats(runs=10, sr=171.0, balls=10)
        assert calculate_batting_points(stats) == 10 + 6

    def test_strike_rate_150_to_170(self):
        stats = self._stats(runs=10, sr=160.0, balls=10)
        assert calculate_batting_points(stats) == 10 + 4

    def test_strike_rate_130_to_150(self):
        stats = self._stats(runs=10, sr=140.0, balls=10)
        assert calculate_batting_points(stats) == 10 + 2

    def test_strike_rate_50_to_59(self):
        stats = self._stats(runs=10, sr=55.0, balls=10)
        assert calculate_batting_points(stats) == 10 - 4

    def test_strike_rate_below_50(self):
        stats = self._stats(runs=10, sr=40.0, balls=10)
        assert calculate_batting_points(stats) == 10 - 6

    def test_strike_rate_ignored_below_10_balls(self):
        # With < 10 balls, SR bracket should not apply
        stats = self._stats(runs=5, sr=40.0, balls=9)
        assert calculate_batting_points(stats) == 5  # no SR penalty


# ---------------------------------------------------------------------------
# calculate_bowling_points
# ---------------------------------------------------------------------------

class TestCalculateBowlingPoints:

    def _stats(self, wickets=0, maidens=0, economy=8.0,
               lbwbowledcount=0, overs=2):
        # Default economy=8.0 is in the neutral zone (7.01–9.99)
        return {'wickets': wickets, 'maidens': maidens, 'economy': economy,
                'lbwbowledcount': lbwbowledcount, 'overs': overs}

    def test_basic_wickets(self):
        stats = self._stats(wickets=2, overs=4, economy=8.0)
        # 2*25 = 50, economy 8.0 is neutral (no bonus/penalty), no milestone
        assert calculate_bowling_points(stats) == 50

    def test_wicket_milestone_3(self):
        stats = self._stats(wickets=3, overs=4, economy=8.0)
        # 3*25 + 4 = 79
        assert calculate_bowling_points(stats) == 79

    def test_wicket_milestone_4(self):
        stats = self._stats(wickets=4, overs=4, economy=8.0)
        # 4*25 + 8 = 108
        assert calculate_bowling_points(stats) == 108

    def test_wicket_milestone_5_plus(self):
        stats = self._stats(wickets=5, overs=4, economy=8.0)
        # 5*25 + 16 = 141
        assert calculate_bowling_points(stats) == 141

    def test_maiden_overs(self):
        stats = self._stats(wickets=1, maidens=2, overs=4, economy=8.0)
        # 25 + 12*2 = 49
        assert calculate_bowling_points(stats) == 49

    def test_lbw_bowled_bonus(self):
        stats = self._stats(wickets=2, lbwbowledcount=1, overs=4, economy=8.0)
        # 2*25 + 8*1 = 58
        assert calculate_bowling_points(stats) == 58

    def test_economy_below_5(self):
        stats = self._stats(wickets=0, overs=4, economy=4.5)
        assert calculate_bowling_points(stats) == 6

    def test_economy_5_to_599(self):
        stats = self._stats(wickets=0, overs=4, economy=5.5)
        assert calculate_bowling_points(stats) == 4

    def test_economy_6_to_7(self):
        stats = self._stats(wickets=0, overs=4, economy=6.5)
        assert calculate_bowling_points(stats) == 2

    def test_economy_10_to_11(self):
        stats = self._stats(wickets=0, overs=4, economy=10.5)
        assert calculate_bowling_points(stats) == -2

    def test_economy_11_to_12(self):
        stats = self._stats(wickets=0, overs=4, economy=11.5)
        assert calculate_bowling_points(stats) == -4

    def test_economy_above_12(self):
        stats = self._stats(wickets=0, overs=4, economy=13.0)
        assert calculate_bowling_points(stats) == -6

    def test_economy_ignored_below_2_overs(self):
        stats = self._stats(wickets=0, overs=1, economy=4.0)
        # overs < 2 → no economy bonus
        assert calculate_bowling_points(stats) == 0


# ---------------------------------------------------------------------------
# calculate_fielding_points
# ---------------------------------------------------------------------------

class TestCalculateFieldingPoints:

    def _stats(self, catches=0, runouts=0, stumpings=0):
        return {'catches': catches, 'runouts': runouts, 'stumpings': stumpings}

    def test_single_catch(self):
        assert calculate_fielding_points(self._stats(catches=1)) == 8

    def test_three_catches_bonus(self):
        # 3*8 + 4 bonus = 28
        assert calculate_fielding_points(self._stats(catches=3)) == 28

    def test_stumpings(self):
        assert calculate_fielding_points(self._stats(stumpings=1)) == 12

    def test_runouts(self):
        assert calculate_fielding_points(self._stats(runouts=1)) == 8

    def test_combined(self):
        stats = self._stats(catches=2, runouts=1, stumpings=1)
        # 2*8 + 8 + 12 = 36
        assert calculate_fielding_points(stats) == 36


# ---------------------------------------------------------------------------
# calculate_total_points
# ---------------------------------------------------------------------------

class TestCalculateTotalPoints:

    def _player(self, name='Test Player', batting=None, bowling=None, fielding=None):
        p = {'player_name': name}
        if batting is not None:
            p['batting'] = batting
        if bowling is not None:
            p['bowling'] = bowling
        if fielding is not None:
            p['fielding'] = fielding
        return p

    def test_batting_only(self):
        batting = {'runs': 20, 'fours': 0, 'sixes': 0, 'sr': 100.0, 'isOut': False, 'balls': 10}
        result = calculate_total_points(self._player(batting=batting))
        assert result['batting points'] == 20
        assert result['bowling points'] == 0
        assert result['fielding points'] == 0
        assert result['total_points'] == 20

    def test_all_disciplines(self):
        batting = {'runs': 50, 'fours': 0, 'sixes': 0, 'sr': 100.0, 'isOut': False, 'balls': 30}
        bowling = {'wickets': 2, 'maidens': 0, 'economy': 8.0, 'lbwbowledcount': 0, 'overs': 4}
        fielding = {'catches': 1, 'runouts': 0, 'stumpings': 0}
        result = calculate_total_points(
            self._player(batting=batting, bowling=bowling, fielding=fielding))
        assert result['batting points'] == 58   # 50 + 8 milestone
        assert result['bowling points'] == 50   # 2*25, economy 8.0 neutral
        assert result['fielding points'] == 8   # 1 catch
        assert result['total_points'] == 116

    def test_no_disciplines(self):
        result = calculate_total_points(self._player())
        assert result['total_points'] == 0

    def test_player_name_in_result(self):
        result = calculate_total_points(self._player(name='Virat Kohli'))
        assert result['playername'] == 'Virat Kohli'
