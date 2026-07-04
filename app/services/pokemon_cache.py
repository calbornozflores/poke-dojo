"""In-memory cache of the static ~1025-row `pokemon` table.

Battle Arena picks a random unused Pokémon plus wrong-answer options on every
round. Doing that via `ORDER BY RANDOM()` against remote Postgres costs
several full-table-sort round trips per round. Since the table barely ever
changes during a session, we cache it once and do selection in Python.
"""
from __future__ import annotations

import random
import threading
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Pokemon


@dataclass(frozen=True)
class PokemonLite:
    id: int
    name: str
    generation: int
    sprite_url: str


_cache: list[PokemonLite] = []
_by_id: dict[int, PokemonLite] = {}
_by_first_letter: dict[str, list[PokemonLite]] = {}
_by_generation: dict[int, list[PokemonLite]] = {}
_lock = threading.Lock()


def is_warm() -> bool:
    return bool(_cache)


def warm_cache(db: Session) -> int:
    """Load all Pokémon into memory. No-op if already warm."""
    global _cache, _by_id, _by_first_letter, _by_generation
    with _lock:
        if _cache:
            return len(_cache)
        rows = db.execute(
            select(Pokemon.id, Pokemon.name, Pokemon.generation, Pokemon.sprite_url)
        ).all()
        cache = [PokemonLite(r.id, r.name, r.generation, r.sprite_url) for r in rows]
        by_id: dict[int, PokemonLite] = {}
        by_letter: dict[str, list[PokemonLite]] = {}
        by_gen: dict[int, list[PokemonLite]] = {}
        for p in cache:
            by_id[p.id] = p
            by_letter.setdefault(p.name[0].upper(), []).append(p)
            by_gen.setdefault(p.generation, []).append(p)
        _cache, _by_id, _by_first_letter, _by_generation = cache, by_id, by_letter, by_gen
        return len(_cache)


def get_by_id(pokemon_id: int) -> PokemonLite | None:
    return _by_id.get(pokemon_id)


def pick_unused(exclude_ids: set[int]) -> PokemonLite | None:
    pool = [p for p in _cache if p.id not in exclude_ids] or _cache
    return random.choice(pool) if pool else None


def pick_wrong_options(correct: PokemonLite, n: int = 2) -> list[PokemonLite]:
    """Mirrors the original fallback chain: same first letter -> same
    generation -> any, each a full replace (not a union) if the pool has
    fewer than n candidates."""
    letter_pool = [p for p in _by_first_letter.get(correct.name[0].upper(), []) if p.id != correct.id]
    if len(letter_pool) >= n:
        return random.sample(letter_pool, n)

    gen_pool = [p for p in _by_generation.get(correct.generation, []) if p.id != correct.id]
    if len(gen_pool) >= n:
        return random.sample(gen_pool, n)

    any_pool = [p for p in _cache if p.id != correct.id]
    return random.sample(any_pool, min(n, len(any_pool)))
