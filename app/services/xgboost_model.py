"""
Per-user, per-game-type XGBoost model for Challenge Mode.

Trains only on the user's results for the active game type so that accuracy
from Name It does not bleed into Guess Number rankings, etc.
Model artifacts: data/challenge_model_{user_id}_{game_type}.json
"""
from __future__ import annotations
import shutil
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import xgboost as xgb
from sqlalchemy.orm import Session
from app.models import GameResult, Pokemon

MODEL_DIR = Path(__file__).parent.parent.parent / "data"
STAGE_MAP = {"basic": 0, "stage_1": 1, "stage_2": 2}
MIN_RESULTS = 20

TYPE_ENC = {
    "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
    "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10, "water": 11,
    "grass": 12, "electric": 13, "psychic": 14, "ice": 15, "dragon": 16,
    "dark": 17, "fairy": 18,
}

FEATURE_META = {
    "type1":      {"label": "Type 1",       "weakness": "Certain primary types trip you up",     "strength": "You know primary types well"},
    "type2":      {"label": "Type 2",       "weakness": "Dual-type Pokémon are harder for you",  "strength": "Dual-type Pokémon are easy for you"},
    "height":     {"label": "Height",       "weakness": "Taller Pokémon are trickier to guess",  "strength": "You handle Pokémon of all sizes"},
    "weight":     {"label": "Weight",       "weakness": "Heavier Pokémon are harder to guess",   "strength": "Weight doesn't affect your accuracy"},
    "hp":         {"label": "HP",           "weakness": "High-HP Pokémon trip you up",           "strength": "You know your tanks well"},
    "attack":     {"label": "Attack",       "weakness": "Powerhouse Pokémon are tricky",         "strength": "Strong attackers are your forte"},
    "defense":    {"label": "Defense",      "weakness": "Defensive Pokémon give you trouble",    "strength": "Tanky Pokémon are easy for you"},
    "sp_attack":  {"label": "Sp. Atk",     "weakness": "Special attackers stump you",           "strength": "Special attackers are your comfort zone"},
    "sp_defense": {"label": "Sp. Def",     "weakness": "Sp. defensive Pokémon are hard",        "strength": "Sp. defensive Pokémon are a strength"},
    "speed":      {"label": "Speed",        "weakness": "Fast Pokémon trip you up",              "strength": "Speedy Pokémon are your strong suit"},
    "generation": {"label": "Generation",   "weakness": "Certain generations are tricky for you","strength": "You have solid generational knowledge"},
    "stage":      {"label": "Evo. stage",   "weakness": "Evolution stage affects your accuracy", "strength": "You know your evo stages well"},
    "name_length":{"label": "Name length",  "weakness": "Longer names are your weak spot",       "strength": "You handle names of all lengths well"},
    "pokedex_id": {"label": "Pokédex #",    "weakness": "Certain Pokédex ranges trip you up",    "strength": "You know your Pokédex order well"},
}


def _model_path(user_id: int, game_type: str) -> Path:
    return MODEL_DIR / f"challenge_model_{user_id}_{game_type}.json"


def _build_features(pokemon: Pokemon) -> dict:
    return {
        "type1":      TYPE_ENC.get(pokemon.type1, 0),
        "type2":      TYPE_ENC.get(pokemon.type2, 0) if pokemon.type2 else 0,
        "height":     pokemon.height or 0,
        "weight":     pokemon.weight or 0,
        "hp":         pokemon.hp,
        "attack":     pokemon.attack,
        "defense":    pokemon.defense,
        "sp_attack":  pokemon.sp_attack,
        "sp_defense": pokemon.sp_defense,
        "speed":      pokemon.speed,
        "generation": pokemon.generation,
        "stage":      STAGE_MAP.get(pokemon.stage, 0),
        "name_length":len(pokemon.name),
        "pokedex_id": pokemon.id,
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

    rows = []
    for r in results:
        poke = db.query(Pokemon).get(r.pokemon_id)
        if poke is None:
            continue
        feat = _build_features(poke)
        feat["error_rate"] = 100.0 - r.accuracy
        rows.append(feat)

    if not rows:
        return False

    df = pd.DataFrame(rows)
    X = df.drop(columns=["error_rate"])
    y = df["error_rate"]

    model = xgb.XGBRegressor()
    model.fit(X, y)

    MODEL_DIR.mkdir(exist_ok=True)
    dest = _model_path(user_id, game_type)
    tmp = dest.with_suffix(".tmp")
    model.save_model(str(tmp))
    shutil.move(str(tmp), str(dest))
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

    all_pokemon = db.query(Pokemon).all()
    rows = []
    for poke in all_pokemon:
        feat = _build_features(poke)
        feat["pokemon_id"] = poke.id
        rows.append(feat)

    df = pd.DataFrame(rows)
    pokemon_ids = df["pokemon_id"].tolist()
    X = df.drop(columns=["pokemon_id"])

    scores = model.predict(X)
    ranked = sorted(zip(pokemon_ids, scores), key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in ranked[:n]]


def _shap_data(user_id: int, game_type: str, db: Session):
    """Shared helper: load model + compute SHAP values for all Pokémon."""
    path = _model_path(user_id, game_type)
    if not path.exists():
        return None, None, None, None

    model = xgb.XGBRegressor()
    model.load_model(str(path))

    all_pokemon = db.query(Pokemon).all()
    rows = [_build_features(poke) for poke in all_pokemon]
    df = pd.DataFrame(rows)
    feature_names = df.columns.tolist()

    dmat = xgb.DMatrix(df)
    shap_contribs = model.get_booster().predict(dmat, pred_contribs=True)
    shap_vals = shap_contribs[:, :-1]   # drop bias column

    return df, feature_names, shap_vals, model


def get_profile(user_id: int, game_type: str, db: Session) -> dict | None:
    """Return SHAP-based strengths and weaknesses. None if no model exists yet."""
    df, feature_names, shap_vals, _ = _shap_data(user_id, game_type, db)
    if df is None:
        return None

    results = (
        db.query(GameResult)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .count()
    )

    mean_shap = shap_vals.mean(axis=0)
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

    return {
        "weaknesses": [i for i in items if i["is_weakness"]][:4],
        "strengths":  [i for i in items if not i["is_weakness"]][:4],
        "total_games": results,
    }


def get_profile_chart_data(user_id: int, game_type: str, db: Session) -> dict | None:
    """Return structured correct-vs-wrong SHAP data for the in-page bar chart."""
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
    if not results:
        return None

    rows, accs = [], []
    for r in results:
        poke = db.query(Pokemon).get(r.pokemon_id)
        if poke is None:
            continue
        rows.append(_build_features(poke))
        accs.append(r.accuracy)

    if not rows:
        return None

    acc = np.array(accs, dtype=float)
    df = pd.DataFrame(rows)
    feature_names = df.columns.tolist()

    dmat = xgb.DMatrix(df)
    shap_contribs = model.get_booster().predict(dmat, pred_contribs=True)
    abs_shap = np.abs(shap_contribs[:, :-1])

    correct_mask = acc >= 80
    wrong_mask   = acc < 50
    n_correct = int(correct_mask.sum())
    n_wrong   = int(wrong_mask.sum())

    if n_correct == 0 and n_wrong == 0:
        return None

    n_feat = len(feature_names)
    correct_avg = abs_shap[correct_mask].mean(axis=0) if n_correct > 0 else np.zeros(n_feat)
    wrong_avg   = abs_shap[wrong_mask].mean(axis=0)   if n_wrong   > 0 else np.zeros(n_feat)

    gap   = wrong_avg - correct_avg
    order = np.argsort(gap)[::-1]  # biggest weakness first

    features = []
    for i in order:
        features.append({
            "label":       FEATURE_META.get(feature_names[i], {}).get("label", feature_names[i]),
            "correct":     round(float(correct_avg[i]), 5),
            "wrong":       round(float(wrong_avg[i]), 5),
            "is_weakness": float(gap[i]) > 0,
        })

    weakness_vals = [v for f in features if     f["is_weakness"] for v in (f["correct"], f["wrong"])]
    strength_vals = [v for f in features if not f["is_weakness"] for v in (f["correct"], f["wrong"])]
    max_weakness  = float(max(weakness_vals)) if weakness_vals else 1.0
    max_strength  = float(max(strength_vals)) if strength_vals else 1.0

    return {
        "n_correct":    n_correct,
        "n_wrong":      n_wrong,
        "max_weakness": max_weakness,
        "max_strength": max_strength,
        "features":     features,
    }


def get_category_shap(user_id: int, game_type: str, db: Session) -> dict | None:
    """
    Per-category mean SHAP contribution for generation, stage, and type.
    Positive value → feature increases predicted error rate (harder for this user).
    Negative value → feature decreases predicted error rate (easier).
    Returns None if model not trained yet.
    """
    path = _model_path(user_id, game_type)
    if not path.exists():
        return None

    model = xgb.XGBRegressor()
    model.load_model(str(path))

    played = (
        db.query(GameResult, Pokemon)
        .join(Pokemon, GameResult.pokemon_id == Pokemon.id)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .all()
    )
    if not played:
        return None

    rows     = [_build_features(poke) for _, poke in played]
    pokemons = [poke for _, poke in played]

    df = pd.DataFrame(rows)
    fn = df.columns.tolist()
    sv = model.get_booster().predict(xgb.DMatrix(df), pred_contribs=True)[:, :-1]

    gi  = fn.index("generation")
    si  = fn.index("stage")
    t1i = fn.index("type1")
    t2i = fn.index("type2")

    gen_s  = defaultdict(list)
    stg_s  = defaultdict(list)
    typ_s  = defaultdict(list)

    for i, poke in enumerate(pokemons):
        gen_s[poke.generation].append(float(sv[i, gi]))
        stg_s[poke.stage].append(float(sv[i, si]))
        typ_s[poke.type1].append(float(sv[i, t1i]))
        if poke.type2:
            typ_s[poke.type2].append(float(sv[i, t2i]))

    def _avg(lst): return round(sum(lst) / len(lst), 4)

    return {
        "generation": {k: _avg(v) for k, v in gen_s.items()},
        "stage":      {k: _avg(v) for k, v in stg_s.items()},
        "type":       {k: _avg(v) for k, v in typ_s.items()},
    }
