"""
Per-user, per-game-type difficulty analysis for Challenge Mode.

Replaces the previous XGBoost model with direct SQL statistics:
- predict_hardest: sorts Pokémon by the user's own accuracy (lowest = hardest)
- get_category_shap: always returns None (SHAP removed; profile uses accuracy bars)
- train: no-op (stats are computed on-demand, no model files written)
"""
from __future__ import annotations
import random
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models import GameResult, Pokemon


def train(user_id: int, game_type: str, db: Session) -> bool:
    """No-op — difficulty is now computed on-demand from game history."""
    return True


def predict_hardest(user_id: int, game_type: str, db: Session, n: int = 50) -> list[int]:
    """
    Return up to n Pokémon IDs ranked hardest-first for this user and game type.
    Hardness = lowest average accuracy across all attempts.
    Unseen Pokémon are appended in random order (treated as average difficulty).
    """
    results = (
        db.query(GameResult.pokemon_id, GameResult.accuracy)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .all()
    )

    if not results:
        all_ids = [row[0] for row in db.query(Pokemon.id).all()]
        random.shuffle(all_ids)
        return all_ids[:n]

    acc_sum: dict[int, float] = defaultdict(float)
    acc_cnt: dict[int, int] = defaultdict(int)
    for pokemon_id, accuracy in results:
        acc_sum[pokemon_id] += accuracy
        acc_cnt[pokemon_id] += 1

    seen_avg = {pid: acc_sum[pid] / acc_cnt[pid] for pid in acc_sum}
    seen_sorted = sorted(seen_avg.items(), key=lambda x: x[1])  # ascending = hardest first
    ranked = [pid for pid, _ in seen_sorted[:n]]

    if len(ranked) < n:
        seen_set = set(acc_sum.keys())
        all_ids = [row[0] for row in db.query(Pokemon.id).all()]
        unseen = [pid for pid in all_ids if pid not in seen_set]
        random.shuffle(unseen)
        ranked.extend(unseen[: n - len(ranked)])

    return ranked[:n]


def get_category_shap(user_id: int, game_type: str, db: Session) -> dict | None:
    """Always returns None — SHAP removed. Profile uses accuracy bars directly."""
    return None
