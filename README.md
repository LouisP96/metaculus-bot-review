# metaculus-bot-review

Review how a Metaculus forecasting bot performed on the questions it forecast.

`bot-review` builds a table of how your bot's forecasts turned out and attaches the reports it
posted, so you can see what it was thinking on the questions it got wrong. Everything is
read-only and requires no LLM spend. All it needs is `METACULUS_TOKEN`.

It reads the reports your bot published as Metaculus comments, so it works whether or not the
bot saved anything locally. It parses only the format
[forecasting-tools](https://github.com/Metaculus/forecasting-tools) itself writes, so it works
on any bot built on the framework.

## Install

```bash
pip install metaculus-bot-review
```

Or with poetry:

```bash
poetry add metaculus-bot-review
```

Set `METACULUS_TOKEN` in your environment or in a `.env` file in the directory you run from.
That token is what decides which bot gets reviewed.

## Scoring your questions

```bash
bot-review review --tournament <slug-or-id> --output review.json --summary review.md
bot-review review --resolved-since 30              # anything that resolved recently
bot-review review --post 44328 44326               # specific questions
bot-review review --from-json review.json --top 3  # re-render without refetching
```

The markdown summary gives your leaderboard standing, how many questions were forecast and
scored, and the best and worst questions ranked on whichever score the leaderboard uses — spot
peer for the AI benchmark tournaments, time-averaged peer for the Metaculus Cup.

The JSON adds per-question detail: the official scores, the bot's forecast, and one `RunTrace`
per run taken from the comment that run posted — each forecaster's prediction, the run time,
and, when the bot publishes its cost metadata, what the run cost and how long it took.
`QuestionOutcome.trace` picks the run that was standing when the question was spot scored,
which is the one that earned the score.

## Reading the reasoning

Reasoning text is not stored in the table. Pull it a piece at a time:

```bash
bot-review show 44328 --section research
bot-review show 44328 --forecaster R1:F3 --comment 921582  # a specific run
```

Sections are `summary`, `research` and `forecasts`. A research section runs to tens of
thousands of characters, so on a question whose resolution you already know it is usually
cheaper to search it than to read it:

```bash
bot-review show 44328 --section research | grep -niE "death toll" | head
```

## From Python

```python
from metaculus_bot_review.outcomes import get_tournament_outcomes
from metaculus_bot_review.summary import build_summary
from metaculus_bot_review.traces import attach_traces, get_trace

table = get_tournament_outcomes("minibench-2026-06-29")
attach_traces(table)
print(build_summary(table))
print(get_trace(44328, section="research"))
```

## Agent skill

[`skill/SKILL.md`](skill/SKILL.md) drives the whole loop with an agent which builds the table, decides on
the questions worth investigating, reads the reports and writes the review.

Copy it into your bot's repo to use it with Claude Code:

```bash
mkdir -p .claude/skills/review-bot
curl -o .claude/skills/review-bot/SKILL.md \
    https://raw.githubusercontent.com/LouisP96/metaculus-bot-review/main/skill/SKILL.md
```

Then ask it to review the bot.

## Rate limits

Metaculus rate-limits at roughly 5 requests per second. The CLI spaces requests by 0.7s;
change it with `--seconds-between-requests`.

## License

MIT
