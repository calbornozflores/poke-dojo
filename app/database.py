from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_PATH = Path(__file__).parent.parent / "data" / "pokemon.db"
DB_PATH.parent.mkdir(exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def run_migrations():
    """Add any missing columns to existing tables without losing data."""
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
