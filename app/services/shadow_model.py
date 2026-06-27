"""
Per-user Shadow opponent for Solo Challenge.

Replaces the previous XGBoost model with direct SQL statistics:
- predict: average of the user's actual response times for that Pokémon,
           falling back to their overall average when no per-Pokémon data exists.
- model_exists: always True (stats are available as soon as any results exist)
- train: no-op (computed on-demand, no model files written)
"""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.models import CompetitiveMatch, CompetitiveResult


def model_exists(username: str) -> bool:
    """Always True — stats are computed on-demand from existing results."""
    return True


def train(username: str, db: Session) -> bool:
    """No-op — response-time stats are computed on-demand."""
    return True


def predict(username: str, pokemon_id: int, shadow_level: float, db: Session) -> int | None:
    """
    Predict the user's response time (ms) for this Pokémon.
    shadow_level is accepted for API compatibility but not used.

    1. Returns the mean of all correct response times for this specific Pokémon.
    2. Falls back to the mean across ALL Pokémon if none exist for this one.
    3. Returns None if the user has no response-time data at all.
    """
    match_ids = (
        db.query(CompetitiveMatch.id)
        .filter(CompetitiveMatch.player1 == username, CompetitiveMatch.mode == "single")
        .subquery()
    )

    base = (
        db.query(CompetitiveResult.player1_response_ms)
        .join(match_ids, CompetitiveResult.match_id == match_ids.c.id)
        .filter(
            CompetitiveResult.player1_was_correct == True,  # noqa: E712
            CompetitiveResult.player1_response_ms.isnot(None),
        )
    )

    poke_times = [
        r[0] for r in base.filter(CompetitiveResult.pokemon_id == pokemon_id).all()
    ]
    if poke_times:
        return max(0, int(round(sum(poke_times) / len(poke_times))))

    all_times = [r[0] for r in base.all()]
    if all_times:
        return max(0, int(round(sum(all_times) / len(all_times))))

    return None
