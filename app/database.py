import os
import re
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Normalize Supabase transaction-pooler URLs for psycopg2:
    # strip ?pgbouncer=true and switch port 6543 → 5432 (session pooler)
    _url = re.sub(r'[?&]pgbouncer=true', '', DATABASE_URL)
    _url = re.sub(r':6543/', ':5432/', _url)
    engine = create_engine(_url, pool_pre_ping=True)
else:
    DB_PATH = Path(__file__).parent.parent / "data" / "pokemon.db"
    DB_PATH.parent.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def run_migrations():
    """Add any missing columns to existing SQLite databases. Skipped in PostgreSQL mode."""
    if DATABASE_URL:
        return  # Fresh PostgreSQL schema is managed by create_all()

    with engine.connect() as conn:
        for col, ddl in [("height", "INTEGER DEFAULT 0"), ("weight", "INTEGER DEFAULT 0")]:
            try:
                conn.execute(text(f"ALTER TABLE pokemon ADD COLUMN {col} {ddl}"))
                conn.commit()
            except Exception:
                pass

        # Phase 2: add time_used and final_score to game_results.
        # When time_used is first added (migration needed), delete old scoreless rows.
        time_used_added = False
        for col, ddl in [("time_used", "REAL"), ("final_score", "REAL")]:
            try:
                conn.execute(text(f"ALTER TABLE game_results ADD COLUMN {col} {ddl}"))
                conn.commit()
                if col == "time_used":
                    time_used_added = True
            except Exception:
                pass

        if time_used_added:
            conn.execute(text("DELETE FROM game_results"))
            conn.commit()

        # Phase 3: shadow_predicted_ms column for competitive_results
        try:
            conn.execute(text("ALTER TABLE competitive_results ADD COLUMN shadow_predicted_ms INTEGER"))
            conn.commit()
        except Exception:
            pass

        # Phase 4: shadow_level column for competitive_results
        try:
            conn.execute(text("ALTER TABLE competitive_results ADD COLUMN shadow_level REAL DEFAULT 0"))
            conn.commit()
        except Exception:
            pass

        # Phase 5: daily challenge streak tracking on users
        for col, ddl in [
            ("current_streak",      "INTEGER DEFAULT 0"),
            ("last_challenge_date", "TEXT DEFAULT NULL"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
                conn.commit()
            except Exception:
                pass

        # Phase 6: trainer XP for level system
        for col, ddl in [("total_xp", "REAL DEFAULT 0.0")]:
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
                conn.commit()
            except Exception:
                pass

        # Phase 7: base_experience per species (0 = not yet fetched, triggers re-fetch)
        for col, ddl in [("base_experience", "INTEGER DEFAULT 0")]:
            try:
                conn.execute(text(f"ALTER TABLE pokemon ADD COLUMN {col} {ddl}"))
                conn.commit()
            except Exception:
                pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
