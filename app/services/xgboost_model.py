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


def generate_profile_image(user_id: int, game_type: str, db: Session) -> str | None:
    """
    Generate a SHAP beeswarm-style summary image for the user/game_type.
    Returns base64-encoded PNG or None if no model exists.
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

    dmat = xgb.DMatrix(df)
    shap_contribs = model.get_booster().predict(dmat, pred_contribs=True)
    shap_vals = shap_contribs[:, :-1]   # (n_pokemon, n_features)

    # Sort features by mean |SHAP| descending
    mean_abs = np.abs(shap_vals).mean(axis=0)
    order = np.argsort(mean_abs)          # ascending → bottom of chart
    feat_sorted  = [feature_names[i] for i in order]
    shap_sorted  = shap_vals[:, order]
    feat_vals_sorted = df.values[:, order]

    labels = [FEATURE_META.get(f, {}).get("label", f) for f in feat_sorted]
    n_feat = len(feat_sorted)

    # ── Figure ────────────────────────────────────────────────────────────────
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
    ax.xaxis.label.set_color(MUTED)

    mean_shap = shap_vals.mean(axis=0)

    for i, fi in enumerate(order):
        sv   = shap_sorted[:, i]             # SHAP values for this feature
        fv   = feat_vals_sorted[:, i]        # raw feature values
        ms   = float(mean_shap[fi])

        # Normalise feature values to [0,1] for colormap
        fv_min, fv_max = fv.min(), fv.max()
        fv_norm = (fv - fv_min) / (fv_max - fv_min + 1e-9)

        # Jitter dots vertically
        jitter = np.random.default_rng(fi).uniform(-0.3, 0.3, len(sv))

        # Color: red = high feature value, blue = low feature value
        colors = plt.cm.RdBu_r(fv_norm)

        ax.scatter(sv, np.full(len(sv), i) + jitter,
                   c=colors, s=6, alpha=0.55, linewidths=0)

        # Mean SHAP vertical tick
        col = RED if ms > 0 else GREEN
        ax.plot([ms, ms], [i - 0.38, i + 0.38], color=col, lw=2.5, zorder=5)

    ax.axvline(0, color="#2a3a5c", lw=1.5, zorder=1)
    ax.set_yticks(range(n_feat))
    ax.set_yticklabels(labels, fontsize=9, color=TEXT)
    ax.set_xlabel("SHAP value  (→ harder,  ← easier)", color=MUTED, fontsize=9)

    # Legend
    patch_w = mpatches.Patch(color=RED,   label="Weakness (pushes difficulty up)")
    patch_s = mpatches.Patch(color=GREEN, label="Strength (pulls difficulty down)")
    legend = ax.legend(handles=[patch_w, patch_s], loc="lower right",
                       fontsize=8, framealpha=0.25,
                       facecolor=SURFACE, edgecolor="#2a3a5c",
                       labelcolor=TEXT)

    # Colorbar proxy
    sm = plt.cm.ScalarMappable(cmap="RdBu_r", norm=plt.Normalize(0, 1))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.01, fraction=0.015)
    cbar.ax.tick_params(colors=MUTED, labelsize=7)
    cbar.set_label("Feature value\n(low → high)", color=MUTED, fontsize=7)
    cbar.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color=MUTED)
    cbar.outline.set_edgecolor("#2a3a5c")
    cbar.ax.set_facecolor(BG)

    ax.set_title(
        f"SHAP Feature Impact  ·  {len(results)} games",
        color=TEXT, fontsize=10, pad=10,
    )

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()
