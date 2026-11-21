from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from forecasting_tools.helpers.metaculus_client import MetaculusClient

from metaculus_bot_review.client import ReviewClient
from metaculus_bot_review.comment import Comment
from metaculus_bot_review.leaderboard import Leaderboard

# Field names and nesting copied from live API responses on 2026-07-24.
COMMENT_JSON = {
    "id": 977364,
    "on_post": 44676,
    "author": {"id": 305884, "username": "a-bot", "is_bot": True},
    "created_at": "2026-07-24T20:49:49.595398Z",
    "text": "# SUMMARY\n*Final Prediction*: 20.0%",
    "is_private": True,
    "is_text_archived": False,
    "included_forecast": {"start_time": "2026-07-24T20:49:44.998152Z"},
    "parent_id": None,
}

ENTRY_JSON = {
    "user": {"id": 303267, "username": "a-bot", "is_bot": True},
    "rank": 17,
    "score": 348.50171781642365,
    "coverage": 36,
    "contribution_count": 36,
    "medal": None,
    "prize": 0,
    "take": 121453.44732099818,
    "excluded": False,
}

LEADERBOARD_JSON = {
    "id": 932,
    "is_primary_leaderboard": True,
    "project_id": 33064,
    "project_name": "MiniBench - 2026-06-29",
    "project_slug": "minibench-2026-06-29",
    "project_type": "question_series",
    "score_type": "spot_peer_tournament",
    "finalized": True,
    "entries": [ENTRY_JSON],
    "userEntry": ENTRY_JSON,
}


class TestCommentParsing:
    def test_reads_the_live_field_names(self):
        comment = Comment.from_metaculus_api_json(COMMENT_JSON)
        assert comment.id == 977364
        assert comment.on_post == 44676
        assert comment.author_id == 305884
        assert comment.author_username == "a-bot"
        assert comment.is_private
        assert comment.text.startswith("# SUMMARY")
        assert comment.created_at.year == 2026


class TestLeaderboardParsing:
    def test_entry_fields(self):
        leaderboard = Leaderboard.from_metaculus_api_json(LEADERBOARD_JSON)
        assert leaderboard.project_id == 33064
        assert leaderboard.score_type == "spot_peer_tournament"
        assert leaderboard.finalized
        assert len(leaderboard.entries) == 1
        assert leaderboard.user_entry is not None
        assert leaderboard.user_entry.rank == 17
        assert leaderboard.user_entry.user_id == 303267
        assert not leaderboard.user_entry.excluded

    def test_no_entry_when_you_never_forecast_the_tournament(self):
        without_entry = {**LEADERBOARD_JSON, "userEntry": None}
        assert Leaderboard.from_metaculus_api_json(without_entry).user_entry is None

    def test_community_aggregates_rank_alongside_forecasters(self):
        aggregate = {
            **ENTRY_JSON,
            "user": None,
            "aggregation_method": "recency_weighted",
            "rank": 16,
        }
        leaderboard = Leaderboard.from_metaculus_api_json(
            {**LEADERBOARD_JSON, "entries": [ENTRY_JSON, aggregate]}
        )
        crowd = leaderboard.entries[1]
        assert crowd.user_id is None
        assert crowd.username is None
        assert crowd.aggregation_method == "recency_weighted"
        assert leaderboard.entries[0].aggregation_method is None

    def test_a_medalled_entry_keeps_its_medal(self):
        medalled = {
            **LEADERBOARD_JSON,
            "userEntry": {**ENTRY_JSON, "medal": "gold", "rank": 1},
        }
        entry = Leaderboard.from_metaculus_api_json(medalled).user_entry
        assert entry is not None and entry.medal == "gold"


class TestCurrentUserId:
    def test_is_looked_up_once_per_client(self):
        client = ReviewClient(token="a-token", sleep_seconds_between_requests=0)
        with patch.object(
            MetaculusClient, "get_current_user_id", return_value=7
        ) as lookup:
            assert client.get_current_user_id() == 7
            assert client.get_current_user_id() == 7
        lookup.assert_called_once()


class TestGetPostJson:
    def test_returns_the_post_as_the_api_sent_it(self):
        response = MagicMock(status_code=200, content=json.dumps({"id": 1}).encode())
        client = ReviewClient(
            token="a-token", sleep_seconds_between_requests=0, sleep_jitter_seconds=0
        )
        with patch(
            "metaculus_bot_review.client.requests.get", return_value=response
        ) as get:
            assert client.get_post_json(1) == {"id": 1}
        assert get.call_args.args[0].endswith("/posts/1/")


class TestGetOwnComments:
    @pytest.fixture(autouse=True)
    def user_id(self):
        with patch.object(ReviewClient, "get_current_user_id", return_value=305884):
            yield

    def client(self) -> ReviewClient:
        return ReviewClient(token="a-token", sleep_seconds_between_requests=0)

    def test_asks_for_private_comments_by_default(self):
        with patch.object(ReviewClient, "_get_comment_page", return_value=[]) as page:
            self.client().get_own_comments()
        assert page.call_args.args[0]["is_private"] == "true"
        assert page.call_args.args[0]["author"] == 305884

    def test_post_filter_is_only_sent_when_given(self):
        with patch.object(ReviewClient, "_get_comment_page", return_value=[]) as page:
            self.client().get_own_comments()
            assert "post" not in page.call_args.args[0]
            self.client().get_own_comments(post_id=44676)
            assert page.call_args.args[0]["post"] == 44676

    def test_pages_until_a_short_page_arrives(self):
        full_page = [
            COMMENT_JSON
        ] * ReviewClient.MAX_COMMENTS_FROM_COMMENT_API_PER_REQUEST
        with patch.object(
            ReviewClient,
            "_get_comment_page",
            side_effect=[full_page, [COMMENT_JSON]],
        ) as page:
            comments = self.client().get_own_comments()
        assert len(comments) == 101
        assert page.call_count == 2
        assert page.call_args_list[1].args[0]["offset"] == 100
