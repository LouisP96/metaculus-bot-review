"""Metaculus client with the extra reads a review needs."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from forecasting_tools.helpers.metaculus_client import MetaculusClient
from forecasting_tools.util.misc import (
    raise_for_status_with_additional_info,
    retry_with_exponential_backoff,
)

from metaculus_bot_review.comment import Comment
from metaculus_bot_review.leaderboard import Leaderboard

logger = logging.getLogger(__name__)


class ReviewClient(MetaculusClient):
    MAX_COMMENTS_FROM_COMMENT_API_PER_REQUEST = 100

    def get_own_comments(
        self,
        post_id: int | None = None,
        is_private: bool = True,
        user_id: int | None = None,
        max_comments: int = 500,
    ) -> list[Comment]:
        """
        Comments you posted, newest first. The API only allows listing your own.

        :param post_id: only return comments on this post
        :param is_private: whether to return private or public comments
        :param user_id: your own user id, looked up if not given
        :param max_comments: stop paging once this many are collected
        """
        author_id = user_id if user_id is not None else self.get_current_user_id()
        comments: list[Comment] = []
        while len(comments) < max_comments:
            page_size = min(
                self.MAX_COMMENTS_FROM_COMMENT_API_PER_REQUEST,
                max_comments - len(comments),
            )
            params: dict[str, Any] = {
                "author": author_id,
                "is_private": str(is_private).lower(),
                "limit": page_size,
                "offset": len(comments),
            }
            if post_id is not None:
                params["post"] = post_id
            page = self._get_comment_page(params)
            comments.extend(Comment.from_metaculus_api_json(item) for item in page)
            if len(page) < page_size:
                break
        logger.info(f"Retrieved {len(comments)} comments for user {author_id}")
        return comments

    @retry_with_exponential_backoff()
    def _get_comment_page(self, params: dict[str, Any]) -> list[dict]:
        self._sleep_between_requests()
        response = requests.get(
            f"{self.base_url}/comments/",
            params=params,
            **self._get_auth_headers(),  # type: ignore
            timeout=self.timeout,
        )
        raise_for_status_with_additional_info(response)
        return json.loads(response.content)["results"]

    @retry_with_exponential_backoff()
    def get_comment(self, comment_id: int) -> Comment:
        """
        One comment with its full text, including archived text the list endpoint cuts short.

        :param comment_id: the comment's id
        """
        self._sleep_between_requests()
        response = requests.get(
            f"{self.base_url}/comments/{comment_id}/",
            **self._get_auth_headers(),  # type: ignore
            timeout=self.timeout,
        )
        raise_for_status_with_additional_info(response)
        return Comment.from_metaculus_api_json(json.loads(response.content))

    @retry_with_exponential_backoff()
    def get_project_leaderboard(self, project_id: int) -> Leaderboard:
        """
        The primary leaderboard for a project, including your own entry.

        :param project_id: numeric project id (slugs are not accepted here)
        """
        self._sleep_between_requests()
        response = requests.get(
            f"{self.base_url}/leaderboards/project/{project_id}/",
            params={"with_entries": "true"},
            **self._get_auth_headers(),  # type: ignore
            timeout=self.timeout,
        )
        raise_for_status_with_additional_info(response)
        leaderboards = json.loads(response.content)
        primary = next(
            leaderboard
            for leaderboard in leaderboards
            if leaderboard["is_primary_leaderboard"]
        )
        logger.info(
            f"Retrieved leaderboard for project {project_id} with {len(primary.get('entries') or [])} entries"
        )
        return Leaderboard.from_metaculus_api_json(primary)
