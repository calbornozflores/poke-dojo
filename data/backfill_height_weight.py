"""
One-time script to add height and weight to existing Pokémon rows.
Run: uv run python data/backfill_height_weight.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from app.database import SessionLocal, run_migrations
from app.models import Pokemon

run_migrations()

db = SessionLocal()
try:
    missing = db.query(Pokemon).filter(
        (Pokemon.height == None) | (Pokemon.height == 0)
    ).all()

    if not missing:
        print("All Pokémon already have height/weight. Nothing to do.")
        sys.exit(0)

    print(f"Backfilling height/weight for {len(missing)} Pokémon...")
    http = requests.Session()
    http.headers["User-Agent"] = "poke-dojo/1.0"

    for i, poke in enumerate(missing, 1):
        try:
            r = http.get(f"https://pokeapi.co/api/v2/pokemon/{poke.id}", timeout=10)
            r.raise_for_status()
            data = r.json()
            poke.height = data.get("height", 0)
            poke.weight = data.get("weight", 0)
            db.commit()
            print(f"  [{i}/{len(missing)}] {poke.name}: h={poke.height} w={poke.weight}")
        except Exception as e:
            print(f"  [{i}/{len(missing)}] {poke.name}: FAILED ({e})")
        time.sleep(0.15)

    print("Done.")
finally:
    db.close()
