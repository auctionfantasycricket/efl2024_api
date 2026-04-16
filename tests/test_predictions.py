"""Tests for prediction scoring logic."""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers — import scoring functions once implemented
# ---------------------------------------------------------------------------

def make_prediction(match_number, predicted_winner, is_correct=None,
                    correct_points=None, streak_points=None, total_points=None):
    return {
        "matchNumber": match_number,
        "predictedWinner": predicted_winner,
        "isCorrect": is_correct,
        "correctPoints": correct_points,
        "streakPoints": streak_points,
        "totalPoints": total_points,
    }


def score(prior_predictions, predicted_winner, actual_winner):
    """
    Call the real scoring function once it's extracted.
    For now import inline so tests drive the design.
    """
    from predictions import compute_score
    return compute_score(prior_predictions, predicted_winner, actual_winner)


# ---------------------------------------------------------------------------
# compute_score — unit tests (no DB)
# ---------------------------------------------------------------------------

class TestComputeScore:

    def test_single_correct_no_streak(self):
        """First correct prediction: 10 points, no streak bonus."""
        result = score([], "MI", "MI")
        assert result["isCorrect"] is True
        assert result["correctPoints"] == 10
        assert result["streakPoints"] == 0
        assert result["totalPoints"] == 10

    def test_single_wrong(self):
        """Wrong prediction: 0 points."""
        result = score([], "MI", "CSK")
        assert result["isCorrect"] is False
        assert result["correctPoints"] == 0
        assert result["streakPoints"] == 0
        assert result["totalPoints"] == 0

    def test_streak_of_2(self):
        """1 prior correct → streak=2 → streakPoints=2, total=12."""
        prior = [make_prediction(1, "MI", is_correct=True)]
        result = score(prior, "CSK", "CSK")
        assert result["streakPoints"] == 2
        assert result["totalPoints"] == 12

    def test_streak_of_3(self):
        """2 prior correct → streak=3 → streakPoints=3, total=13."""
        prior = [
            make_prediction(1, "MI", is_correct=True),
            make_prediction(2, "CSK", is_correct=True),
        ]
        result = score(prior, "RCB", "RCB")
        assert result["streakPoints"] == 3
        assert result["totalPoints"] == 13

    def test_wrong_after_streak_resets(self):
        """Wrong prediction after streak: correctPoints=0, streakPoints=0."""
        prior = [
            make_prediction(1, "MI", is_correct=True),
            make_prediction(2, "CSK", is_correct=True),
        ]
        result = score(prior, "RCB", "MI")
        assert result["isCorrect"] is False
        assert result["streakPoints"] == 0
        assert result["totalPoints"] == 0

    def test_correct_after_broken_streak(self):
        """Correct after a wrong resets streak to 1 → no bonus."""
        prior = [
            make_prediction(1, "MI", is_correct=True),
            make_prediction(2, "MI", is_correct=True),
            make_prediction(3, "MI", is_correct=False),
        ]
        result = score(prior, "CSK", "CSK")
        assert result["isCorrect"] is True
        assert result["streakPoints"] == 0
        assert result["totalPoints"] == 10

    def test_all_wrong(self):
        """All wrong: zero everything."""
        prior = [
            make_prediction(1, "MI", is_correct=False),
            make_prediction(2, "CSK", is_correct=False),
        ]
        result = score(prior, "RCB", "MI")
        assert result["totalPoints"] == 0

    def test_streak_only_counts_consecutive_from_end(self):
        """Streak counts from the END only — gap in middle doesn't matter."""
        prior = [
            make_prediction(1, "MI", is_correct=True),   # old correct
            make_prediction(2, "MI", is_correct=False),  # break
            make_prediction(3, "CSK", is_correct=True),  # start new streak
        ]
        result = score(prior, "RCB", "RCB")
        # incoming streak = 1 (only match 3 was correct at end), this = correct → streak=2
        assert result["streakPoints"] == 2
        assert result["totalPoints"] == 12


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_already_scored_prediction_is_skipped(self):
        """process_match_result skips predictions where isCorrect is not None."""
        from predictions import process_match_result

        existing_prediction = {
            "_id": "abc",
            "userId": "user1",
            "matchId": 100,
            "matchNumber": 5,
            "predictedWinner": "MI",
            "isCorrect": True,       # already scored
            "correctPoints": 10,
            "streakPoints": 0,
            "totalPoints": 10,
        }

        mock_db = MagicMock()
        # isCorrect is already set → find(isCorrect=None) returns nothing
        mock_db.predictions.find.return_value = []

        with patch("predictions.db", mock_db):
            result = process_match_result(mock_db, matchId=100, winner="MI")

        assert result["predictions_scored"] == 0
        mock_db.predictions.update_one.assert_not_called()

    def test_double_cron_call_no_double_count(self):
        """Second cron call for same match scores 0 predictions."""
        from predictions import process_match_result

        mock_db = MagicMock()
        # All predictions already have isCorrect set
        mock_db.predictions.find.return_value = []

        with patch("predictions.db", mock_db):
            result = process_match_result(mock_db, matchId=100, winner="MI")

        assert result["predictions_scored"] == 0


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

class TestLeaderboard:

    def test_new_user_entry_created(self):
        """First prediction scored → leaderboard entry upserted with correct values."""
        from predictions import update_leaderboard_for_user

        mock_db = MagicMock()
        with patch("predictions.db", mock_db):
            update_leaderboard_for_user(mock_db, user_id="user1",
                                        is_correct=True, points_earned=10,
                                        new_streak=1)

        mock_db.prediction_leaderboard.update_one.assert_called_once()
        call_args = mock_db.prediction_leaderboard.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$inc"]["totalPoints"] == 10
        assert update_doc["$inc"]["totalPredictions"] == 1

    def test_max_streak_updates_when_beaten(self):
        """maxStreak uses $max so it only increases."""
        from predictions import update_leaderboard_for_user

        mock_db = MagicMock()
        with patch("predictions.db", mock_db):
            update_leaderboard_for_user(mock_db, user_id="user1",
                                        is_correct=True, points_earned=13,
                                        new_streak=3)

        call_args = mock_db.prediction_leaderboard.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$max"]["maxStreak"] == 3

    def test_current_streak_set_on_wrong(self):
        """Wrong prediction sets currentStreak to 0."""
        from predictions import update_leaderboard_for_user

        mock_db = MagicMock()
        with patch("predictions.db", mock_db):
            update_leaderboard_for_user(mock_db, user_id="user1",
                                        is_correct=False, points_earned=0,
                                        new_streak=0)

        call_args = mock_db.prediction_leaderboard.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["currentStreak"] == 0


# ---------------------------------------------------------------------------
# GET /predictions/leaderboard
# ---------------------------------------------------------------------------

class TestLeaderboardEndpoint:

    def _make_entry(self, user_id, total_points, current_streak, max_streak):
        return {
            "userId": user_id,
            "totalPoints": total_points,
            "currentStreak": current_streak,
            "maxStreak": max_streak,
        }

    def test_empty_leaderboard_returns_empty_list(self):
        """No entries in prediction_leaderboard → empty array."""
        from predictions import get_leaderboard

        mock_db = MagicMock()
        mock_db.prediction_leaderboard.find.return_value = []
        mock_db.users.find_one.return_value = None

        result = get_leaderboard(mock_db)
        assert result == []

    def test_sorted_by_total_points_descending(self):
        """Higher totalPoints appears first."""
        from predictions import get_leaderboard

        entries = [
            self._make_entry("user1", 30, 2, 3),
            self._make_entry("user2", 85, 5, 7),
            self._make_entry("user3", 50, 1, 4),
        ]

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(return_value=iter(entries))
        mock_db.prediction_leaderboard.find.return_value = mock_cursor
        mock_db.users.find_one.return_value = None

        result = get_leaderboard(mock_db)
        points = [r["totalPoints"] for r in result]
        assert points == sorted(points, reverse=True)

    def test_username_joined_from_users(self):
        """userName pulled from db.users by userId."""
        from predictions import get_leaderboard

        entries = [self._make_entry("user1", 50, 2, 3)]

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(return_value=iter(entries))
        mock_db.prediction_leaderboard.find.return_value = mock_cursor
        mock_db.users.find_one.return_value = {"name": "Sakshar"}

        result = get_leaderboard(mock_db)
        assert result[0]["userName"] == "Sakshar"

    def test_missing_user_falls_back_to_userid(self):
        """If user not found in db.users, fallback to userId."""
        from predictions import get_leaderboard

        entries = [self._make_entry("user_ghost", 20, 1, 1)]

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(return_value=iter(entries))
        mock_db.prediction_leaderboard.find.return_value = mock_cursor
        mock_db.users.find_one.return_value = None

        result = get_leaderboard(mock_db)
        assert result[0]["userName"] == "user_ghost"

    def test_only_expected_fields_returned(self):
        """Response contains only userName, totalPoints, currentStreak, maxStreak."""
        from predictions import get_leaderboard

        entries = [self._make_entry("user1", 40, 2, 4)]

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(return_value=iter(entries))
        mock_db.prediction_leaderboard.find.return_value = mock_cursor
        mock_db.users.find_one.return_value = {"name": "Manali"}

        result = get_leaderboard(mock_db)
        assert set(result[0].keys()) == {"userName", "totalPoints", "currentStreak", "maxStreak"}
