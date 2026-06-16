import random
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, GameResult, Pokemon
from app.services.string_match import name_accuracy
from app.services.pokemon_data import get_random_pokemon, number_accuracy
from app.services import xgboost_model

router = APIRouter(prefix="/game", tags=["game"])

CHALLENGE_THRESHOLD = 20

ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]


def _upsert_user(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _game_count(user_id: int, game_type: str, db: Session) -> int:
    return (
        db.query(GameResult)
        .filter(GameResult.user_id == user_id, GameResult.game_type == game_type)
        .count()
    )


class StartRequest(BaseModel):
    username: str
    game_type: str
    challenge_mode: bool = False


class StartResponse(BaseModel):
    pokemon_id: int
    sprite_url: str
    artwork_url: str
    name: str | None
    challenge_unlocked: bool
    games_played: int
    type_choices: list[str] = []


class SubmitRequest(BaseModel):
    username: str
    pokemon_id: int
    game_type: str
    guess: str
    was_challenge: bool = False


class SubmitResponse(BaseModel):
    accuracy: float
    correct_name: str
    correct_number: int
    distance: int | None
    games_played: int
    challenge_unlocked: bool
    correct_types: list[str] = []
    user_types: list[str] = []


@router.get("/profile")
def game_profile(
    username: str = Query(...),
    game_type: str = Query(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"model_exists": False, "profile": None}
    profile = xgboost_model.get_profile(user.id, game_type, db)
    return {"model_exists": profile is not None, "profile": profile}


@router.get("/profile/image")
def profile_image(
    username: str = Query(...),
    game_type: str = Query(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"model_exists": False, "chart": None, "total_games": 0}
    chart = xgboost_model.get_profile_chart_data(user.id, game_type, db)
    total = (
        db.query(GameResult)
        .filter(GameResult.user_id == user.id, GameResult.game_type == game_type)
        .count()
    )
    return {"model_exists": chart is not None, "chart": chart, "total_games": total}


@router.get("/profile/breakdown")
def profile_breakdown(
    username: str = Query(...),
    game_type: str = Query(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"has_data": False, "total_games": 0, "breakdown": None}

    total = (
        db.query(GameResult)
        .filter(GameResult.user_id == user.id, GameResult.game_type == game_type)
        .count()
    )

    if total < 5:
        return {"has_data": False, "total_games": total, "breakdown": None}

    rows = (
        db.query(GameResult, Pokemon)
        .join(Pokemon, GameResult.pokemon_id == Pokemon.id)
        .filter(GameResult.user_id == user.id, GameResult.game_type == game_type)
        .all()
    )

    gen_acc   = defaultdict(list)
    stage_acc = defaultdict(list)
    type_acc  = defaultdict(list)

    for result, poke in rows:
        gen_acc[poke.generation].append(result.accuracy)
        stage_acc[poke.stage].append(result.accuracy)
        type_acc[poke.type1].append(result.accuracy)
        if poke.type2:
            type_acc[poke.type2].append(result.accuracy)

    MIN_N = 3
    _TYPE_IDS = {
        "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
        "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10, "water": 11,
        "grass": 12, "electric": 13, "psychic": 14, "ice": 15, "dragon": 16,
        "dark": 17, "fairy": 18,
    }
    _CDN = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/types/generation-ix/scarlet-violet"
    _STAGE_ORDER  = {"basic": 0, "stage_1": 1, "stage_2": 2}
    _STAGE_LABELS = {"basic": "Basic", "stage_1": "Stage 1", "stage_2": "Stage 2"}

    def _avg(lst): return round(sum(lst) / len(lst), 1)

    by_generation = [
        {"label": f"Gen {gen}", "avg": _avg(accs), "n": len(accs)}
        for gen, accs in sorted(gen_acc.items())
        if len(accs) >= MIN_N
    ]

    by_stage = [
        {"label": _STAGE_LABELS.get(stage, stage), "avg": _avg(accs), "n": len(accs)}
        for stage, accs in sorted(stage_acc.items(), key=lambda x: _STAGE_ORDER.get(x[0], 99))
        if len(accs) >= MIN_N
    ]

    by_type = sorted([
        {
            "label": t.capitalize(),
            "icon":  f"{_CDN}/{_TYPE_IDS[t]}.png",
            "avg":   _avg(accs),
            "n":     len(accs),
        }
        for t, accs in type_acc.items()
        if len(accs) >= MIN_N and t in _TYPE_IDS
    ], key=lambda x: x["avg"])

    # Attach SHAP per-category if model is trained (20+ games)
    shap = xgboost_model.get_category_shap(user.id, game_type, db)
    if shap:
        _rev_stage = {"Basic": "basic", "Stage 1": "stage_1", "Stage 2": "stage_2"}
        for item in by_generation:
            s = shap["generation"].get(int(item["label"].split()[-1]))
            if s is not None:
                item["shap"] = s
        for item in by_stage:
            s = shap["stage"].get(_rev_stage.get(item["label"], ""))
            if s is not None:
                item["shap"] = s
        for item in by_type:
            s = shap["type"].get(item["label"].lower())
            if s is not None:
                item["shap"] = s

    return {
        "has_data":    True,
        "total_games": total,
        "breakdown": {
            "by_generation": by_generation,
            "by_stage":      by_stage,
            "by_type":       by_type,
        },
    }


@router.post("/start", response_model=StartResponse)
def start_game(req: StartRequest, db: Session = Depends(get_db)):
    user = _upsert_user(req.username, db)
    games_played = _game_count(user.id, req.game_type, db)
    challenge_unlocked = games_played >= CHALLENGE_THRESHOLD

    if req.challenge_mode and challenge_unlocked:
        recent_ids = [
            r.pokemon_id
            for r in db.query(GameResult)
            .filter(GameResult.user_id == user.id, GameResult.game_type == req.game_type)
            .order_by(GameResult.timestamp.desc())
            .limit(10)
            .all()
        ]
        hard_ids = xgboost_model.predict_hardest(user.id, req.game_type, db, n=50)
        candidates = [pid for pid in hard_ids if pid not in recent_ids] or hard_ids
        pokemon_id = random.choice(candidates[:20])
        pokemon = db.query(Pokemon).get(pokemon_id)
    else:
        recent_ids = [
            r.pokemon_id
            for r in db.query(GameResult)
            .filter(GameResult.user_id == user.id)
            .order_by(GameResult.timestamp.desc())
            .limit(10)
            .all()
        ]
        pokemon = get_random_pokemon(db, exclude_ids=recent_ids)

    if not pokemon:
        raise HTTPException(status_code=503, detail="No Pokémon data found. Run the fetch script first.")

    # Build type choices for type games
    type_choices: list[str] = []
    if req.game_type == "type_easy":
        # Correct types + random wrong types to fill 4 slots
        pokemon_types = [t for t in [pokemon.type1, pokemon.type2] if t]
        wrong = [t for t in ALL_TYPES if t not in pokemon_types]
        choices = pokemon_types + random.sample(wrong, 4 - len(pokemon_types))
        random.shuffle(choices)
        type_choices = choices
    elif req.game_type == "type_hard":
        type_choices = list(ALL_TYPES)

    show_name = req.game_type in ("number_guess", "type_easy")

    return StartResponse(
        pokemon_id=pokemon.id,
        sprite_url=pokemon.sprite_url,
        artwork_url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{pokemon.id}.png",
        name=pokemon.name if show_name else None,
        challenge_unlocked=challenge_unlocked,
        games_played=games_played,
        type_choices=type_choices,
    )


@router.post("/submit", response_model=SubmitResponse)
def submit_answer(req: SubmitRequest, db: Session = Depends(get_db)):
    user = _upsert_user(req.username, db)
    pokemon = db.query(Pokemon).get(req.pokemon_id)
    if not pokemon:
        raise HTTPException(status_code=404, detail="Pokémon not found")

    distance = None
    correct_types: list[str] = []
    user_types: list[str] = []

    if req.game_type == "name_guess":
        accuracy = name_accuracy(req.guess, pokemon.name)

    elif req.game_type == "number_guess":
        try:
            guess_num = int(req.guess)
        except ValueError:
            raise HTTPException(status_code=422, detail="guess must be an integer for number_guess")
        distance = abs(guess_num - pokemon.id)
        accuracy = number_accuracy(guess_num, pokemon.id)

    elif req.game_type == "type_easy":
        pokemon_types = [t.lower() for t in [pokemon.type1, pokemon.type2] if t]
        accuracy = 100.0 if req.guess.lower() in pokemon_types else 0.0
        correct_types = [t for t in [pokemon.type1, pokemon.type2] if t]
        user_types = [req.guess.lower()]

    elif req.game_type == "type_hard":
        selected = [t.strip().lower() for t in req.guess.split(",") if t.strip()]
        pokemon_types = [t.lower() for t in [pokemon.type1, pokemon.type2] if t]
        n_types = len(pokemon_types)
        correct_hits = sum(1 for t in selected if t in pokemon_types)
        wrong_hits = sum(1 for t in selected if t not in pokemon_types)
        accuracy = max(0.0, (correct_hits - wrong_hits) / n_types * 100.0) if n_types > 0 else 0.0
        correct_types = [t for t in [pokemon.type1, pokemon.type2] if t]
        user_types = selected

    else:
        raise HTTPException(status_code=422, detail="invalid game_type")

    result = GameResult(
        user_id=user.id,
        pokemon_id=pokemon.id,
        game_type=req.game_type,
        accuracy=accuracy,
        was_challenge=req.was_challenge,
    )
    db.add(result)
    db.commit()

    games_played = _game_count(user.id, req.game_type, db)
    challenge_unlocked = games_played >= CHALLENGE_THRESHOLD

    if challenge_unlocked:
        xgboost_model.train(user.id, req.game_type, db)

    return SubmitResponse(
        accuracy=round(accuracy, 1),
        correct_name=pokemon.name,
        correct_number=pokemon.id,
        distance=distance,
        games_played=games_played,
        challenge_unlocked=challenge_unlocked,
        correct_types=correct_types,
        user_types=user_types,
    )
