"""Baseline tests for validation logic in waivers.py."""
import pytest
from waivers import is_valid, swap_possible


# ---------------------------------------------------------------------------
# is_valid
# ---------------------------------------------------------------------------

class TestIsValid:

    def test_no_pick_no_drop_returns_nd(self):
        code, msg = is_valid('', '', set(), set(), 1)
        assert code == 'ND'

    def test_no_pick_with_drop_returns_np(self):
        code, msg = is_valid('', 'Phil Salt', set(), set(), 1)
        assert code == 'NP'

    def test_pick_already_taken_returns_pt(self):
        code, msg = is_valid('Virat Kohli', 'Phil Salt', {'Virat Kohli'}, set(), 1)
        assert code == 'PT'

    def test_pick_in_unswappable_returns_sw_unswappable(self):
        code, msg = is_valid('Rohit Sharma', 'Phil Salt', set(), {'Rohit Sharma'}, 1)
        assert code == 'SW'
        assert msg == 'Unswappable'

    def test_drop_in_unswappable_returns_sw_unswappable(self):
        code, msg = is_valid('Rohit Sharma', 'Phil Salt', set(), {'Phil Salt'}, 1)
        assert code == 'SW'
        assert msg == 'Unswappable'

    def test_round_4_with_drop_returns_ar(self):
        code, msg = is_valid('Rohit Sharma', 'Phil Salt', set(), set(), 4)
        assert code == 'AR'

    def test_valid_swap_returns_sw_success(self):
        code, msg = is_valid('Rohit Sharma', 'Phil Salt', set(), set(), 1)
        assert code == 'SW'
        assert msg == 'Success'

    def test_round_not_4_allows_success(self):
        for round_num in [1, 2, 3]:
            code, msg = is_valid('Player A', 'Player B', set(), set(), round_num)
            assert code == 'SW'
            assert msg == 'Success'


# ---------------------------------------------------------------------------
# swap_possible (waivers.py)
# ---------------------------------------------------------------------------

class TestWaiversSwapPossible:

    def _owner(self, bat=3, ball=3, ar=2, fCount=2):
        return {'batCount': bat, 'ballCount': ball, 'arCount': ar, 'fCount': fCount}

    def _player(self, role='BATTER', overseas=False):
        return {'player_role': role, 'isOverseas': overseas}

    def test_valid_same_role_swap(self):
        owner = self._owner()
        drop = self._player(role='BATTER', overseas=False)
        pick = self._player(role='BATTER', overseas=False)
        status, msg = swap_possible(owner, drop, pick)
        assert status == 'success'

    def test_violates_bat_count_minimum(self):
        # batCount=2 → after dropping a batter it becomes 1 < 2
        owner = self._owner(bat=2)
        drop = self._player(role='BATTER')
        pick = self._player(role='BOWLER')
        status, msg = swap_possible(owner, drop, pick)
        assert status == 'failure'

    def test_violates_ball_count_minimum(self):
        owner = self._owner(ball=2)
        drop = self._player(role='BOWLER')
        pick = self._player(role='BATTER')
        status, msg = swap_possible(owner, drop, pick)
        assert status == 'failure'

    def test_violates_ar_count_minimum(self):
        owner = self._owner(ar=2)
        drop = self._player(role='ALL_ROUNDER')
        pick = self._player(role='BATTER')
        status, msg = swap_possible(owner, drop, pick)
        assert status == 'failure'

    def test_violates_fcount_minimum(self):
        # fCount=1 → drop overseas player → 0 < 1
        owner = self._owner(fCount=1)
        drop = self._player(role='BATTER', overseas=True)
        pick = self._player(role='BATTER', overseas=False)
        status, msg = swap_possible(owner, drop, pick)
        assert status == 'failure'

    def test_violates_fcount_maximum(self):
        # fCount=3 → add another overseas → 4 > 3
        owner = self._owner(fCount=3)
        drop = self._player(role='BATTER', overseas=False)
        pick = self._player(role='BATTER', overseas=True)
        status, msg = swap_possible(owner, drop, pick)
        assert status == 'failure'

    def test_neutral_fcount_both_overseas(self):
        owner = self._owner(fCount=2)
        drop = self._player(role='BATTER', overseas=True)
        pick = self._player(role='BATTER', overseas=True)
        status, msg = swap_possible(owner, drop, pick)
        assert status == 'success'
