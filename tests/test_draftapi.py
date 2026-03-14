"""Baseline tests for draft swap validation logic in draftapi.py."""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# swap_possible (draftapi.py)
# Constraints: batCount>=4, ballCount>=4, arCount>=1, wkCount>=1
# Associate nations add to fCount; wicketkeeper affects batCount+wkCount
# ---------------------------------------------------------------------------

class TestDraftApiSwapPossible:

    def _teamdict(self, name, bat=4, ball=4, ar=1, wk=1, fCount=0):
        return {name: {'batCount': bat, 'ballCount': ball, 'arCount': ar,
                       'wkCount': wk, 'fCount': fCount}}

    def _patch_roles(self, in_role, in_country, out_role, out_country):
        """Patch getRoleAndCountry to return given values for in/out players."""
        def side_effect(player):
            if player == 'InPlayer':
                return in_role, in_country
            return out_role, out_country
        return patch('draftapi.getRoleAndCountry', side_effect=side_effect)

    def test_player_not_found_returns_false(self):
        from draftapi import swap_possible
        team = 'TeamA'
        td = self._teamdict(team)
        with patch('draftapi.getRoleAndCountry', return_value=(None, None)):
            assert swap_possible(team, td, 'InPlayer', 'OutPlayer') is False

    def test_valid_batter_for_batter_swap(self):
        from draftapi import swap_possible
        team = 'TeamA'
        td = self._teamdict(team, bat=5)
        with self._patch_roles('batter', 'India', 'batter', 'India'):
            # in: +1 bat → 6, out: -1 bat → 5 → still >=4 → True
            assert swap_possible(team, td, 'InPlayer', 'OutPlayer') is True

    def test_swap_fails_bat_count_too_low(self):
        from draftapi import swap_possible
        team = 'TeamA'
        td = self._teamdict(team, bat=4)
        with self._patch_roles('bowler', 'India', 'batter', 'India'):
            # in: +1 ball → 5, out: -1 bat → 3 < 4 → False
            assert swap_possible(team, td, 'InPlayer', 'OutPlayer') is False

    def test_swap_fails_ball_count_too_low(self):
        from draftapi import swap_possible
        team = 'TeamA'
        td = self._teamdict(team, ball=4)
        with self._patch_roles('batter', 'India', 'bowler', 'India'):
            # in: +1 bat, out: -1 ball → 3 < 4 → False
            assert swap_possible(team, td, 'InPlayer', 'OutPlayer') is False

    def test_associate_nation_increments_fcount(self):
        from draftapi import swap_possible
        team = 'TeamA'
        td = self._teamdict(team, bat=5)
        # Swap out an India batter, swap in a Canada batter → fCount goes 0→1
        # Does not affect pass/fail directly but tests logic runs without error
        with self._patch_roles('batter', 'Canada', 'batter', 'India'):
            # Still satisfies bat>=4, ball>=4, ar>=1, wk>=1
            result = swap_possible(team, td, 'InPlayer', 'OutPlayer')
            assert isinstance(result, bool)

    def test_wicketkeeper_in_adjusts_bat_and_wk(self):
        from draftapi import swap_possible
        team = 'TeamA'
        # wk at minimum: dropping wk then adding bat would fail if wkCount goes <1
        td = self._teamdict(team, bat=4, wk=1)
        with self._patch_roles('wicketkeeper', 'India', 'wicketkeeper', 'India'):
            # in: +1 bat, +1 wk; out: -1 bat, -1 wk → net neutral → True
            assert swap_possible(team, td, 'InPlayer', 'OutPlayer') is True

    def test_wicketkeeper_out_reduces_wk(self):
        from draftapi import swap_possible
        team = 'TeamA'
        td = self._teamdict(team, bat=5, wk=1)
        with self._patch_roles('batter', 'India', 'wicketkeeper', 'India'):
            # out: -1 bat → 4, -1 wk → 0 < 1 → False
            assert swap_possible(team, td, 'InPlayer', 'OutPlayer') is False


# ---------------------------------------------------------------------------
# check_criteria (draftapi.py)
# ---------------------------------------------------------------------------

class TestCheckCriteria:

    def setup_method(self):
        from draftapi import check_criteria
        self._fn = check_criteria

    def _teamdict(self, name, bat=5, ball=5, ar=2, wk=1, fCount=0):
        return {name: {'batCount': bat, 'ballCount': ball, 'arCount': ar,
                       'wkCount': wk, 'fCount': fCount}}

    def test_empty_out_arr_returns_false(self):
        success, out_ret, arr = self._fn('TeamA', {}, 'InPlayer', [])
        assert success is False
        assert out_ret == ''
        assert arr == []

    def test_empty_string_in_arr_returns_false(self):
        success, out_ret, arr = self._fn('TeamA', {}, 'InPlayer', [''])
        assert success is False

    def test_x_entries_skipped(self):
        # All X → falls through to empty string check after skipping
        success, out_ret, arr = self._fn('TeamA', {}, 'InPlayer', ['X', ''])
        assert success is False

    def test_swap_possible_true_returns_success(self):
        team = 'TeamA'
        td = self._teamdict(team)
        with patch('draftapi.swap_possible', return_value=True):
            success, out_ret, arr = self._fn(team, td, 'InPlayer', ['OutPlayer'])
        assert success is True
        assert out_ret == 'OutPlayer'
        assert arr == ['X']

    def test_swap_possible_false_returns_failure(self):
        team = 'TeamA'
        td = self._teamdict(team)
        with patch('draftapi.swap_possible', return_value=False):
            success, out_ret, arr = self._fn(team, td, 'InPlayer', ['OutPlayer'])
        assert success is False
        assert out_ret == 'OutPlayer'

    def test_x_skipped_then_valid_swap(self):
        team = 'TeamA'
        td = self._teamdict(team)
        with patch('draftapi.swap_possible', return_value=True):
            success, out_ret, arr = self._fn(
                team, td, 'InPlayer', ['X', 'OutPlayer'])
        assert success is True
        assert out_ret == 'OutPlayer'
        assert arr == ['X', 'X']
