"""
Pokémon data fetch with live progress tracking.
Runs in a thread executor so the FastAPI event loop stays responsive.
Progress is stored in a module-level dict read by /api/status.
"""
import time
import asyncio
import requests
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Pokemon

TOTAL = 1025

_state: dict = {
    "fetched": 0,
    "total": TOTAL,
    "done": False,
    "running": False,
    "needed": False,  # True if fetch was required on startup
}

GEN_RANGES = [
    (1, 151, 1), (152, 251, 2), (252, 386, 3), (387, 493, 4),
    (494, 649, 5), (650, 721, 6), (722, 809, 7), (810, 905, 8),
    (906, 1025, 9),
]


def get_progress() -> dict:
    return _state.copy()


def _get_generation(pokedex_id: int) -> int:
    for lo, hi, gen in GEN_RANGES:
        if lo <= pokedex_id <= hi:
            return gen
    return 9


def _get_stage(pokemon_id: int, http: requests.Session) -> str:
    try:
        r = http.get(f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_id}/", timeout=10)
        r.raise_for_status()
        chain_url = r.json()["evolution_chain"]["url"]
        r2 = http.get(chain_url, timeout=10)
        r2.raise_for_status()

        def find_depth(node, depth=0):
            sid = int(node["species"]["url"].rstrip("/").split("/")[-1])
            if sid == pokemon_id:
                return depth
            for child in node.get("evolves_to", []):
                result = find_depth(child, depth + 1)
                if result is not None:
                    return result
            return None

        depth = find_depth(r2.json()["chain"])
        return ["basic", "stage_1", "stage_2"][min(depth or 0, 2)]
    except Exception:
        return "basic"


def _fetch_one(pokemon_id: int, http: requests.Session) -> dict | None:
    try:
        r = http.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_id}/", timeout=10)
        r.raise_for_status()
        data = r.json()
        stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}
        types = [t["type"]["name"] for t in data["types"]]
        sprite = (
            data["sprites"]["front_default"]
            or (data["sprites"].get("other") or {})
            .get("official-artwork", {})
            .get("front_default")
        )
        return {
            "id": pokemon_id,
            "name": data["name"],
            "generation": _get_generation(pokemon_id),
            "stage": _get_stage(pokemon_id, http),
            "sprite_url": sprite or "",
            "type1": types[0] if types else "normal",
            "type2": types[1] if len(types) > 1 else None,
            "hp": stats.get("hp", 0),
            "attack": stats.get("attack", 0),
            "defense": stats.get("defense", 0),
            "sp_attack": stats.get("special-attack", 0),
            "sp_defense": stats.get("special-defense", 0),
            "speed": stats.get("speed", 0),
        }
    except Exception:
        return None


def run_fetch_sync() -> None:
    """Blocking fetch — call via run_in_executor from async context."""
    _state["running"] = True
    _state["done"] = False

    db: Session = SessionLocal()
    try:
        existing = {
            row[0]
            for row in db.execute(
                Pokemon.__table__.select().with_only_columns(Pokemon.__table__.c.id)
            )
        }
        _state["fetched"] = len(existing)

        http = requests.Session()
        http.headers["User-Agent"] = "poke-dojo/1.0"

        for pokemon_id in range(1, TOTAL + 1):
            if pokemon_id in existing:
                continue
            data = _fetch_one(pokemon_id, http)
            if data:
                db.add(Pokemon(**data))
                db.commit()
            _state["fetched"] += 1
            time.sleep(0.3)
    finally:
        db.close()
        _state["running"] = False
        _state["done"] = True


async def fetch_all_pokemon_background() -> None:
    """Launch the blocking fetch in a thread without blocking the event loop."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_fetch_sync)


def check_db_ready() -> bool:
    """Return True if the Pokémon table already has data."""
    db: Session = SessionLocal()
    try:
        return db.query(Pokemon).count() >= TOTAL
    except Exception:
        return False
    finally:
        db.close()
