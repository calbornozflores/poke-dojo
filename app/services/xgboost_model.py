"""
Per-user, per-game-type XGBoost model for Challenge Mode.

Trains only on the user's results for the active game type so that accuracy
from Name It does not bleed into Guess Number rankings, etc.
Model artifacts: data/challenge_model_{user_id}_{game_type}.json
"""
from __future__ import annotations
from pathlib import Path
import base64
import io
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
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
    "type1":      {"label": "Primary type",    "weakness": "Certain primary types trip you up",     "strength": "You know primary types well"},
    "type2":      {"label": "Secondary type",  "weakness": "Dual-type Pokémon are harder for you",  "strength": "Dual-type Pokémon are easy for you"},
    "height":     {"label": "Height",          "weakness": "Taller Pokémon are trickier to guess",  "strength": "You handle Pokémon of all sizes"},
    "weight":     {"label": "Weight",          "weakness": "Heavier Pokémon are harder to guess",   "strength": "Weight doesn't affect your accuracy"},
    "hp":         {"label": "Base HP",         "weakness": "High-HP Pokémon trip you up",           "strength": "You know your tanks well"},
    "attack":     {"label": "Attack stat",     "weakness": "Powerhouse Pokémon are tricky",         "strength": "Strong attackers are your forte"},
    "defense":    {"label": "Defense stat",    "weakness": "Defensive Pokémon give you trouble",    "strength": "Tanky Pokémon are easy for you"},
    "sp_attack":  {"label": "Sp. Attack",      "weakness": "Special attackers stump you",           "strength": "Special attackers are your comfort zone"},
    "sp_defense": {"label": "Sp. Defense",     "weakness": "Sp. defensive Pokémon are hard",        "strength": "Sp. defensive Pokémon are a strength"},
    "speed":      {"label": "Speed",           "weakness": "Fast Pokémon trip you up",              "strength": "Speedy Pokémon are your strong suit"},
    "generation": {"label": "Generation",      "weakness": "Certain generations are tricky for you","strength": "You have solid generational knowledge"},
    "stage":      {"label": "Evolution stage", "weakness": "Evolution stage affects your accuracy", "strength": "You know your evo stages well"},
    "name_length":{"label": "Name length",     "weakness": "Longer names are your weak spot",       "strength": "You handle names of all lengths well"},
    "pokedex_id": {"label": "Pokédex range",   "weakness": "Certain Pokédex ranges trip you up",    "strength": "You know your Pokédex order well"},
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


def generate_profile_image(user_id: int, game_type: str, db: Session) -> str | None:
    """Generate a SHAP beeswarm image. Returns base64 PNG or None."""
    df, feature_names, shap_vals, _ = _shap_data(user_id, game_type, db)
    if df is None:
        return None

    total_games = (
        db.query(GameResult)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .count()
    )

    mean_abs = np.abs(shap_vals).mean(axis=0)
    order = np.argsort(mean_abs)          # ascending → bottom of chart
    feat_sorted      = [feature_names[i] for i in order]
    shap_sorted      = shap_vals[:, order]
    feat_vals_sorted = df.values[:, order]
    mean_shap        = shap_vals.mean(axis=0)
    labels           = [FEATURE_META.get(f, {}).get("label", f) for f in feat_sorted]
    n_feat           = len(feat_sorted)

    BG      = "#0d1117"
    SURFACE = "#16213e"
    TEXT    = "#e8eaf6"
    MUTED   = "#8892b0"
    RED     = "#f87171"
    GREEN   = "#4ade80"

    fig, ax = plt.subplots(figsize=(7, max(3.2, n_feat * 0.36 + 0.6)))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2a3a5c")
    ax.tick_params(colors=MUTED, labelsize=9)

    for i, fi in enumerate(order):
        sv = shap_sorted[:, i]
        fv = feat_vals_sorted[:, i].astype(float)
        ms = float(mean_shap[fi])

        fv_min, fv_max = fv.min(), fv.max()
        fv_norm = (fv - fv_min) / (fv_max - fv_min + 1e-9)
        jitter  = np.random.default_rng(fi).uniform(-0.3, 0.3, len(sv))

        ax.scatter(sv, np.full(len(sv), i) + jitter,
                   c=plt.cm.RdBu_r(fv_norm), s=6, alpha=0.55, linewidths=0)

        col = RED if ms > 0 else GREEN
        ax.plot([ms, ms], [i - 0.38, i + 0.38], color=col, lw=2.5, zorder=5)

    ax.axvline(0, color="#2a3a5c", lw=1.5, zorder=1)
    ax.set_yticks(range(n_feat))
    ax.set_yticklabels(labels, fontsize=9, color=TEXT)
    ax.set_xlabel("Impact on difficulty  (→ harder,  ← easier)", color=MUTED, fontsize=9)

    patch_w = mpatches.Patch(color=RED,   label="Weakness")
    patch_s = mpatches.Patch(color=GREEN, label="Strength")
    ax.legend(handles=[patch_w, patch_s], loc="lower right", fontsize=8,
              framealpha=0.25, facecolor=SURFACE, edgecolor="#2a3a5c", labelcolor=TEXT)

    sm = plt.cm.ScalarMappable(cmap="RdBu_r", norm=plt.Normalize(0, 1))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.01, fraction=0.015)
    cbar.ax.tick_params(colors=MUTED, labelsize=7)
    cbar.set_label("Feature value\n(low → high)", color=MUTED, fontsize=7)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color=MUTED)
    cbar.outline.set_edgecolor("#2a3a5c")
    cbar.ax.set_facecolor(BG)

    ax.set_title(f"Feature Impact on Your Difficulty  ·  {total_games} games", color=TEXT, fontsize=10, pad=10)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()
