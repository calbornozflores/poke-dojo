"""In-process cache of per-match ephemeral gameplay state: which Pokémon
have already appeared this match, so /round/next avoids re-querying
Postgres for the used-ids relationship on every round.

Safe as a plain in-process dict: the app runs as a single Fly.io machine,
single uvicorn process, no --workers.

If the process restarts mid-match (Fly can auto-stop/restart the machine),
rehydrate() rebuilds this state from Postgres on the next request for that
match_id. No game history is ever lost since results are already committed
before this cache is updated.
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
    used_pokemon_ids: set[int] = field(default_factory=set)


_matches: "OrderedDict[int, MatchState]" = OrderedDict()
_lock = threading.Lock()


def _evict_if_full() -> None:
    while len(_matches) > _MAX_MATCHES:
        _matches.popitem(last=False)


def start(match_id: int, mode: str) -> MatchState:
    """Called once from /match/start (and defensively from rehydrate())."""
    state = MatchState(mode=mode)
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
    state = start(match_id, match.mode)
    used = db.execute(
        select(CompetitiveResult.pokemon_id).where(CompetitiveResult.match_id == match_id)
    ).scalars().all()
    state.used_pokemon_ids = set(used)
    return state


def record_round(match_id: int, pokemon_id: int) -> None:
    state = _matches.get(match_id)
    if not state:
        return
    state.used_pokemon_ids.add(pokemon_id)


def discard(match_id: int) -> None:
    _matches.pop(match_id, None)
