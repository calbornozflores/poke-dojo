from __future__ import annotations
from pathlib import Path
import pandas as pd
import xgboost as xgb
from sqlalchemy.orm import Session
from app.models import CompetitiveMatch, CompetitiveResult, Pokemon

MODEL_DIR = Path(__file__).parent.parent.parent / "data"
STAGE_MAP = {"basic": 0, "stage_1": 1, "stage_2": 2}
MIN_RESULTS = 20

TYPE_ENC = {
    "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
    "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10, "water": 11,
    "grass": 12, "electric": 13, "psychic": 14, "ice": 15, "dragon": 16,
    "dark": 17, "fairy": 18,
}


def _model_path(username: str) -> Path:
    safe = username.replace("/", "_").replace("\\", "_").replace(" ", "_")
    return MODEL_DIR / f"shadow_model_{safe}.json"


def model_exists(username: str) -> bool:
    return _model_path(username).exists()


def _build_features(pokemon: Pokemon) -> dict:
    return {
        "type1":       TYPE_ENC.get(pokemon.type1, 0),
        "type2":       TYPE_ENC.get(pokemon.type2, 0) if pokemon.type2 else 0,
        "height":      pokemon.height or 0,
        "weight":      pokemon.weight or 0,
        "hp":          pokemon.hp,
        "attack":      pokemon.attack,
        "defense":     pokemon.defense,
        "sp_attack":   pokemon.sp_attack,
        "sp_defense":  pokemon.sp_defense,
        "speed":       pokemon.speed,
        "generation":  pokemon.generation,
        "stage":       STAGE_MAP.get(pokemon.stage, 0),
        "name_length": len(pokemon.name),
        "pokedex_id":  pokemon.id,
    }


def train(username: str, db: Session) -> bool:
    """Train a response-time regression model for this player. Returns True if successful."""
    matches = (
        db.query(CompetitiveMatch)
        .filter(CompetitiveMatch.player1 == username, CompetitiveMatch.mode == "single")
        .all()
    )
    if not matches:
        return False

    match_ids = [m.id for m in matches]
    results = (
        db.query(CompetitiveResult)
        .filter(
            CompetitiveResult.match_id.in_(match_ids),
            CompetitiveResult.player1_was_correct == True,  # noqa: E712
            CompetitiveResult.player1_response_ms.isnot(None),
        )
        .all()
    )

    if len(results) < MIN_RESULTS:
        return False

    rows = []
    for r in results:
        poke = db.get(Pokemon, r.pokemon_id)
        if poke is None:
            continue
        feat = _build_features(poke)
        feat["shadow_level"] = r.shadow_level if r.shadow_level is not None else 0.0
        feat["response_ms"] = r.player1_response_ms
        rows.append(feat)

    if len(rows) < MIN_RESULTS:
        return False

    df = pd.DataFrame(rows)
    X = df.drop(columns=["response_ms"])
    y = df["response_ms"]

    model = xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1)
    model.fit(X, y)

    MODEL_DIR.mkdir(exist_ok=True)
    model.save_model(str(_model_path(username)))
    return True


def predict(username: str, pokemon_id: int, shadow_level: float, db: Session) -> int | None:
    """Predict response time (ms) for this player on this pokemon. None if no model."""
    path = _model_path(username)
    if not path.exists():
        return None

    poke = db.get(Pokemon, pokemon_id)
    if poke is None:
        return None

    model = xgb.XGBRegressor()
    model.load_model(str(path))

    feat = _build_features(poke)
    feat["shadow_level"] = shadow_level
    df = pd.DataFrame([feat])
    try:
        predicted = float(model.predict(df)[0])
    except Exception:
        # Stale model trained on different features — delete and force rebuild
        path.unlink(missing_ok=True)
        return None
    return max(0, int(round(predicted)))
