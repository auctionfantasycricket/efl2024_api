"""Baseline tests for update_owner_items logic in main.py and draftapi.py."""
import pytest


# ---------------------------------------------------------------------------
# main.py update_owner_items
# (purse deduction, role counts, maxBid formula, overseas flag)
# ---------------------------------------------------------------------------

class TestMainUpdateOwnerItems:

    def setup_method(self):
        from main import update_owner_items
        self._fn = update_owner_items

    def _owner(self, purse=1000, total=5, bat=2, ball=2, ar=1, fCount=1):
        return {
            'currentPurse': purse,
            'totalCount': total,
            'batCount': bat,
            'ballCount': ball,
            'arCount': ar,
            'fCount': fCount,
            'maxBid': 0,
        }

    def _player(self, role='BATTER', bought_for=100, overseas=False):
        return {'player_role': role, 'boughtFor': bought_for, 'isOverseas': overseas}

    def test_purse_deducted(self):
        owner = self._owner(purse=1000)
        self._fn(owner, self._player(bought_for=200))
        assert owner['currentPurse'] == 800

    def test_total_count_incremented(self):
        owner = self._owner(total=5)
        self._fn(owner, self._player())
        assert owner['totalCount'] == 6

    def test_max_bid_formula(self):
        # After buying: purse=800, totalCount=6
        # maxBid = 800 - 20*(15 - 6 - 1) = 800 - 20*8 = 640
        owner = self._owner(purse=1000, total=5)
        self._fn(owner, self._player(bought_for=200))
        assert owner['maxBid'] == 800 - 20 * (15 - 6 - 1)

    def test_batter_role_count(self):
        owner = self._owner(bat=2)
        self._fn(owner, self._player(role='BATTER'))
        assert owner['batCount'] == 3

    def test_bowler_role_count(self):
        owner = self._owner(ball=2)
        self._fn(owner, self._player(role='BOWLER'))
        assert owner['ballCount'] == 3

    def test_allrounder_role_count(self):
        owner = self._owner(ar=1)
        self._fn(owner, self._player(role='ALL_ROUNDER'))
        assert owner['arCount'] == 2

    def test_unknown_role_no_count_change(self):
        owner = self._owner(bat=2, ball=2, ar=1)
        self._fn(owner, self._player(role='WICKETKEEPER'))
        assert owner['batCount'] == 2
        assert owner['ballCount'] == 2
        assert owner['arCount'] == 1

    def test_overseas_increments_fcount(self):
        owner = self._owner(fCount=1)
        self._fn(owner, self._player(overseas=True))
        assert owner['fCount'] == 2

    def test_domestic_no_fcount_change(self):
        owner = self._owner(fCount=1)
        self._fn(owner, self._player(overseas=False))
        assert owner['fCount'] == 1


# ---------------------------------------------------------------------------
# draftapi.py update_owner_items
# (totalCount, role counts, draftSequence fill, overseas flag)
# ---------------------------------------------------------------------------

class TestDraftApiUpdateOwnerItems:

    def setup_method(self):
        from draftapi import update_owner_items
        self._fn = update_owner_items

    def _owner(self, total=5, bat=2, ball=2, ar=1, fCount=1, sequence=None):
        owner = {
            'totalCount': total,
            'batCount': bat,
            'ballCount': ball,
            'arCount': ar,
            'fCount': fCount,
        }
        if sequence is not None:
            owner['draftSequence'] = sequence
        return owner

    def _player(self, name='Player A', role='BATTER', overseas=False):
        return {'player_name': name, 'player_role': role, 'isOverseas': overseas}

    def test_total_count_incremented(self):
        owner = self._owner()
        self._fn(owner, self._player())
        assert owner['totalCount'] == 6

    def test_batter_role_count(self):
        owner = self._owner(bat=2)
        self._fn(owner, self._player(role='BATTER'))
        assert owner['batCount'] == 3

    def test_bowler_role_count(self):
        owner = self._owner(ball=2)
        self._fn(owner, self._player(role='BOWLER'))
        assert owner['ballCount'] == 3

    def test_allrounder_role_count(self):
        owner = self._owner(ar=1)
        self._fn(owner, self._player(role='ALL_ROUNDER'))
        assert owner['arCount'] == 2

    def test_overseas_increments_fcount(self):
        owner = self._owner(fCount=1)
        self._fn(owner, self._player(overseas=True))
        assert owner['fCount'] == 2

    def test_domestic_no_fcount_change(self):
        owner = self._owner(fCount=1)
        self._fn(owner, self._player(overseas=False))
        assert owner['fCount'] == 1

    def test_draft_sequence_fills_first_empty(self):
        owner = self._owner(sequence=['Alice', '', 'Bob', ''])
        self._fn(owner, self._player(name='Charlie'))
        assert owner['draftSequence'] == ['Alice', 'Charlie', 'Bob', '']

    def test_draft_sequence_no_empty_slot_unchanged(self):
        owner = self._owner(sequence=['Alice', 'Bob'])
        self._fn(owner, self._player(name='Charlie'))
        assert owner['draftSequence'] == ['Alice', 'Bob']

    def test_draft_sequence_initialized_if_missing(self):
        owner = self._owner()  # no draftSequence key
        self._fn(owner, self._player(name='NewPlayer'))
        assert 'draftSequence' in owner
        assert owner['draftSequence'] == []
