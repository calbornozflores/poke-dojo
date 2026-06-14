"""
Manual one-time data fetch — use this if you want to pre-populate the DB
before starting the server (optional; the server fetches automatically).

Run: uv run python data/fetch_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import engine
from app.models import Base
from app.services.data_loader import run_fetch_sync, _state, TOTAL

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print(f"Fetching {TOTAL} Pokémon from PokeAPI...")

    # Monkey-patch state to print progress
    import time
    import threading

    def _print_progress():
        while not _state["done"]:
            fetched = _state["fetched"]
            pct = int((fetched / TOTAL) * 100)
            bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
            print(f"\r  [{bar}] {pct:3d}% ({fetched}/{TOTAL})", end="", flush=True)
            time.sleep(1)
        print(f"\r  [{'#' * 50}] 100% ({TOTAL}/{TOTAL})")

    t = threading.Thread(target=_print_progress, daemon=True)
    t.start()

    run_fetch_sync()
    print(f"\nDone. Database: {Path(__file__).parent / 'pokemon.db'}")
