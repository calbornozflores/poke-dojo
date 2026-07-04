"""In-process cache of per-match ephemeral gameplay state: which Pokémon
have already appeared this match, and this player's historical shadow-model
response times.

Every CompetitiveResult row is still written synchronously to Postgres on
/round/submit (the shared leaderboard's source of truth) — this cache only
holds derived state that lets next_round/submit_round skip redundant reads.
Safe as a plain in-process dict: the app runs as a single Fly.io machine,
single uvicorn process, no --workers.

If the process restarts mid-match (Fly can auto-stop/restart the machine),
rehydrate() rebuilds this state from Postgres on the next request for that
match_id — costs a couple of queries once, then it's cached again. No game
history is ever lost since results are already committed before this cache
is updated.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompetitiveMatch, CompetitiveResult

_MAX_MATCHES = 500


@dataclass
class MatchState:
    mode: str
    player1: str
    used_pokemon_ids: set[int] = field(default_factory=set)
    poke_times: dict[int, list[int]] = field(default_factory=dict)
    all_times: list[int] = field(default_factory=list)


_matches: "OrderedDict[int, MatchState]" = OrderedDict()
_lock = threading.Lock()


def _evict_if_full() -> None:
    while len(_matches) > _MAX_MATCHES:
        _matches.popitem(last=False)


def start(match_id: int, mode: str, player1: str, db: Session) -> MatchState:
    """Called once from /match/start (and defensively from rehydrate()).
    Prefetches this player's cross-match shadow-model history in ONE query
    so later /round/submit calls do zero extra reads for shadow prediction."""
    state = MatchState(mode=mode, player1=player1)
    if mode == "single":
        rows = db.execute(
            select(CompetitiveResult.pokemon_id, CompetitiveResult.player1_response_ms)
            .join(CompetitiveMatch, CompetitiveResult.match_id == CompetitiveMatch.id)
            .where(
                CompetitiveMatch.player1 == player1,
                CompetitiveMatch.mode == "single",
                CompetitiveResult.player1_was_correct.is_(True),
                CompetitiveResult.player1_response_ms.isnot(None),
            )
        ).all()
        for pid, ms in rows:
            state.poke_times.setdefault(pid, []).append(ms)
            state.all_times.append(ms)
    with _lock:
        _matches[match_id] = state
        _matches.move_to_end(match_id)
        _evict_if_full()
    return state


def get(match_id: int) -> MatchState | None:
    state = _matches.get(match_id)
    if state is not None:
        _matches.move_to_end(match_id)
    return state


def rehydrate(match_id: int, db: Session) -> MatchState | None:
    """Fallback if the process restarted mid-match and match_id is missing
    from the in-memory dict. Rebuilds from Postgres."""
    match = db.get(CompetitiveMatch, match_id)
    if not match:
        return None
    state = start(match_id, match.mode, match.player1, db)
    used = db.execute(
        select(CompetitiveResult.pokemon_id).where(CompetitiveResult.match_id == match_id)
    ).scalars().all()
    state.used_pokemon_ids = set(used)
    return state


def record_round(match_id: int, pokemon_id: int, was_correct: bool, response_ms: int | None) -> None:
    state = _matches.get(match_id)
    if not state:
        return
    state.used_pokemon_ids.add(pokemon_id)
    if state.mode == "single" and was_correct and response_ms is not None:
        state.poke_times.setdefault(pokemon_id, []).append(response_ms)
        state.all_times.append(response_ms)


def predict(match_id: int, pokemon_id: int) -> int | None:
    state = _matches.get(match_id)
    if not state:
        return None
    times = state.poke_times.get(pokemon_id)
    if times:
        return max(0, round(sum(times) / len(times)))
    if state.all_times:
        return max(0, round(sum(state.all_times) / len(state.all_times)))
    return None


def discard(match_id: int) -> None:
    _matches.pop(match_id, None)
