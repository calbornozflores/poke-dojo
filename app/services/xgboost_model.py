"""
Per-user, per-game-type XGBoost model for Challenge Mode.

Trains only on the user's results for the active game type so that accuracy
from Name It does not bleed into Guess Number rankings, etc.
Model artifacts: data/challenge_model_{user_id}_{game_type}.json
"""
from pathlib import Path
import numpy as np
import pandas as pd
import xgboost as xgb
from sqlalchemy.orm import Session
from app.models import GameResult, Pokemon

FEATURE_META = {
    "avg_accuracy": {
        "label": "Familiar Pokémon",
        "weakness": "Past exposure isn't helping your recall",
        "strength": "You reliably nail Pokémon you've seen before",
    },
    "prior_attempts": {
        "label": "Repeated practice",
        "weakness": "Repetition isn't improving your accuracy yet",
        "strength": "Practice is clearly paying off",
    },
    "hp":        {"label": "Base HP",       "weakness": "High-HP Pokémon trip you up",          "strength": "You know your tanks well"},
    "attack":    {"label": "Attack stat",   "weakness": "Powerhouse Pokémon are tricky",         "strength": "Strong attackers are your forte"},
    "defense":   {"label": "Defense stat",  "weakness": "Defensive Pokémon give you trouble",    "strength": "Tanky Pokémon are easy for you"},
    "sp_attack": {"label": "Sp. Attack",    "weakness": "Special attackers stump you",           "strength": "Special attackers are your comfort zone"},
    "sp_defense":{"label": "Sp. Defense",   "weakness": "Sp. defensive Pokémon are hard",        "strength": "Sp. defensive Pokémon are a strength"},
    "speed":     {"label": "Speed",         "weakness": "Fast Pokémon trip you up",              "strength": "Speedy Pokémon are your strong suit"},
    "generation":{"label": "Generation",    "weakness": "Certain generations are tricky for you","strength": "You have solid generational knowledge"},
    "stage":     {"label": "Evolution stage","weakness": "Evolution stage affects your accuracy", "strength": "You know your evo stages well"},
    "name_length":{"label": "Name length",  "weakness": "Longer names are your weak spot",       "strength": "You handle names of all lengths well"},
    "pokedex_id":{"label": "Pokédex range", "weakness": "Certain Pokédex ranges trip you up",    "strength": "You know your Pokédex order well"},
}

MODEL_DIR = Path(__file__).parent.parent.parent / "data"
STAGE_MAP = {"basic": 0, "stage_1": 1, "stage_2": 2}
MIN_RESULTS = 20


def _model_path(user_id: int, game_type: str) -> Path:
    return MODEL_DIR / f"challenge_model_{user_id}_{game_type}.json"


def _build_features(pokemon: Pokemon, user_history: dict) -> dict:
    hist = user_history.get(pokemon.id, {"count": 0, "avg_accuracy": 50.0})
    return {
        "prior_attempts": hist["count"],
        "avg_accuracy": hist["avg_accuracy"],
        "hp": pokemon.hp,
        "attack": pokemon.attack,
        "defense": pokemon.defense,
        "sp_attack": pokemon.sp_attack,
        "sp_defense": pokemon.sp_defense,
        "speed": pokemon.speed,
        "generation": pokemon.generation,
        "stage": STAGE_MAP.get(pokemon.stage, 0),
        "name_length": len(pokemon.name),
        "pokedex_id": pokemon.id,
    }


def _build_history(results) -> dict:
    history: dict[int, dict] = {}
    for r in results:
        if r.pokemon_id not in history:
            history[r.pokemon_id] = {"count": 0, "total_acc": 0.0}
        history[r.pokemon_id]["count"] += 1
        history[r.pokemon_id]["total_acc"] += r.accuracy
    return {
        pid: {"count": v["count"], "avg_accuracy": v["total_acc"] / v["count"]}
        for pid, v in history.items()
    }


def train(user_id: int, game_type: str, db: Session) -> bool:
    """Train the per-game-type model for a user. Returns True if successful."""
    results = (
        db.query(GameResult)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .all()
    )
    if len(results) < MIN_RESULTS:
        return False

    user_history = _build_history(results)

    rows = []
    for r in results:
        poke = db.query(Pokemon).get(r.pokemon_id)
        if poke is None:
            continue
        feat = _build_features(poke, user_history)
        feat["error_rate"] = 100.0 - r.accuracy
        rows.append(feat)

    if not rows:
        return False

    df = pd.DataFrame(rows)
    X = df.drop(columns=["error_rate"])
    y = df["error_rate"]

    model = xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42)
    model.fit(X, y)

    MODEL_DIR.mkdir(exist_ok=True)
    model.save_model(str(_model_path(user_id, game_type)))
    return True


def predict_hardest(user_id: int, game_type: str, db: Session, n: int = 50) -> list[int]:
    """
    Return up to n Pokémon IDs ranked hardest-first for this user and game type.
    Falls back to random if not enough data to train yet.
    """
    import random

    path = _model_path(user_id, game_type)
    if not path.exists():
        trained = train(user_id, game_type, db)
        if not trained:
            all_ids = [row[0] for row in db.query(Pokemon).with_entities(Pokemon.id).all()]
            return random.sample(all_ids, min(n, len(all_ids)))

    model = xgb.XGBRegressor()
    model.load_model(str(path))

    results = (
        db.query(GameResult)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .all()
    )
    user_history = _build_history(results)

    all_pokemon = db.query(Pokemon).all()
    rows = []
    for poke in all_pokemon:
        feat = _build_features(poke, user_history)
        feat["pokemon_id"] = poke.id
        rows.append(feat)

    df = pd.DataFrame(rows)
    pokemon_ids = df["pokemon_id"].tolist()
    X = df.drop(columns=["pokemon_id"])

    scores = model.predict(X)
    ranked = sorted(zip(pokemon_ids, scores), key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in ranked[:n]]


def get_profile(user_id: int, game_type: str, db: Session) -> dict | None:
    """
    Return SHAP-based strengths and weaknesses for the user in this game type.
    Returns None if no trained model exists yet.
    """
    path = _model_path(user_id, game_type)
    if not path.exists():
        return None

    model = xgb.XGBRegressor()
    model.load_model(str(path))

    results = (
        db.query(GameResult)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .all()
    )
    user_history = _build_history(results)

    all_pokemon = db.query(Pokemon).all()
    rows = [_build_features(poke, user_history) for poke in all_pokemon]
    df = pd.DataFrame(rows)
    feature_names = df.columns.tolist()

    # XGBoost native SHAP — no extra library needed
    dmat = xgb.DMatrix(df)
    shap_contribs = model.get_booster().predict(dmat, pred_contribs=True)
    shap_values = shap_contribs[:, :-1]  # drop bias column

    mean_shap = shap_values.mean(axis=0)

    items = []
    for i, feat in enumerate(feature_names):
        ms = float(mean_shap[i])
        meta = FEATURE_META.get(feat, {"label": feat, "weakness": f"{feat} is a weak spot", "strength": f"{feat} is a strength"})
        items.append({
            "feature": feat,
            "label": meta["label"],
            "description": meta["weakness"] if ms > 0 else meta["strength"],
            "mean_shap": round(ms, 3),
            "abs_shap": abs(ms),
            "is_weakness": ms > 0,
        })

    items.sort(key=lambda x: x["abs_shap"], reverse=True)

    max_abs = items[0]["abs_shap"] if items else 1.0
    for item in items:
        item["magnitude"] = round(item["abs_shap"] / max_abs * 100, 1)
        del item["abs_shap"]

    weaknesses = [i for i in items if i["is_weakness"]][:4]
    strengths  = [i for i in items if not i["is_weakness"]][:4]

    return {
        "weaknesses": weaknesses,
        "strengths": strengths,
        "total_games": len(results),
    }
