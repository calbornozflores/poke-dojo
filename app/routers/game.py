import random
from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/start", response_model=StartResponse)
def start_game(req: StartRequest, db: Session = Depends(get_db)):
    user = _upsert_user(req.username, db)
    games_played = _game_count(user.id, req.game_type, db)
    challenge_unlocked = games_played >= CHALLENGE_THRESHOLD

    if req.challenge_mode and challenge_unlocked:
        recent_ids = [
            r.pokemon_id
            for r in db.query(GameResult)
            .filter(GameResult.user_id == user.id)
            .order_by(GameResult.timestamp.desc())
            .limit(10)
            .all()
        ]
        hard_ids = xgboost_model.predict_hardest(user.id, db, n=50)
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
        xgboost_model.train(user.id, db)

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
