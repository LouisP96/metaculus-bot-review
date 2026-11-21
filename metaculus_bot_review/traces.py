"""Attach the bot's own comments to an outcome table as run traces.

The comment a bot posts is its report, so it is the trace of that run. A
question can have several, one per run; the one that earned the score is the
run standing when the question was spot scored.
"""

from __future__ import annotations

import re
from collections import defaultdict

from metaculus_bot_review.client import ReviewClient
from metaculus_bot_review.comment import Comment
from metaculus_bot_review.outcomes import OutcomeTable, RunTrace
from metaculus_bot_review.report_parsing import (
    final_prediction,
    forecaster_rationales,
    parse_forecasters,
    split_sections,
    was_truncated,
)

COST_PATTERN = re.compile(r"^\*Total Cost\*:\s*\$([\d.]+)", re.MULTILINE)
MINUTES_PATTERN = re.compile(r"^\*Time Spent\*:\s*([\d.]+) minutes", re.MULTILINE)
QUESTION_PATTERN = re.compile(r"^\*Question\*:(.*)$", re.MULTILINE)


def reduce_comment(comment: Comment) -> RunTrace:
    """Reduce a posted report to the fields a review needs."""
    summary = split_sections(comment.text).get("summary", "")
    question = QUESTION_PATTERN.search(comment.text)
    cost = COST_PATTERN.search(comment.text)
    minutes = MINUTES_PATTERN.search(comment.text)
    return RunTrace(
        comment_id=comment.id,
        run_time=comment.created_at,
        question_text=question.group(1).strip() if question else None,
        final_prediction=final_prediction(summary),
        forecasters=parse_forecasters(summary),
        cost=float(cost.group(1)) if cost else None,
        minutes=float(minutes.group(1)) if minutes else None,
        truncated=was_truncated(comment.text),
    )


def _own_comments_on_post(client: ReviewClient, post_id: int) -> list[Comment]:
    """Your private and public comments on a post."""
    return [
        comment
        for is_private in (True, False)
        for comment in client.get_own_comments(post_id=post_id, is_private=is_private)
    ]


def attach_traces(table: OutcomeTable, client: ReviewClient | None = None) -> None:
    """
    Fill in ``traces`` on every question in the table from your comments on its post.

    :param table: the table to attach to, modified in place
    :param client: client to fetch with, created from the environment if not given
    """
    client = client or ReviewClient()
    rows_by_post = defaultdict(list)
    for outcome in table.questions:
        rows_by_post[outcome.post_id].append(outcome)
    for post_id, rows in rows_by_post.items():
        runs = [
            reduce_comment(
                client.get_comment(comment.id) if comment.is_text_archived else comment
            )
            for comment in _own_comments_on_post(client, post_id)
        ]
        for outcome in rows:
            outcome.traces = (
                runs
                if len(rows) == 1
                else [run for run in runs if run.question_text == outcome.title]
            )


def get_trace(
    post_id: int,
    section: str = "research",
    forecaster: str | None = None,
    comment_id: int | None = None,
    client: ReviewClient | None = None,
) -> str:
    """
    One part of a report the bot posted, by default its latest on the post.

    Raises if the post has no comments from you, the comment is on another post,
    or the report has no such section or forecaster.

    :param post_id: post id, as it appears in question urls
    :param section: summary, research or forecasts
    :param forecaster: a key like ``R1:F2``, to read that rationale instead
    :param comment_id: a trace's ``comment_id``, to read that run instead
    :param client: client to fetch with, created from the environment if not given
    """
    client = client or ReviewClient()
    if comment_id is None:
        comments = _own_comments_on_post(client, post_id)
        if not comments:
            raise ValueError(f"You have no comments on post {post_id}")
        comment_id = max(comments, key=lambda comment: comment.created_at).id
    comment = client.get_comment(comment_id)
    if comment.on_post != post_id:
        raise ValueError(
            f"Comment {comment_id} is on post {comment.on_post}, not {post_id}"
        )
    if forecaster:
        return forecaster_rationales(comment.text)[forecaster]
    return split_sections(comment.text)[section]
