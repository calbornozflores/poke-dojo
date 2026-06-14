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


def _upsert_user(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _game_count(user_id: int, db: Session) -> int:
    return db.query(GameResult).filter(GameResult.user_id == user_id).count()


class StartRequest(BaseModel):
    username: str
    game_type: str  # name_guess | number_guess
    challenge_mode: bool = False


class StartResponse(BaseModel):
    pokemon_id: int
    sprite_url: str
    name: str | None  # None for game1, provided for game2
    challenge_unlocked: bool
    games_played: int


class SubmitRequest(BaseModel):
    username: str
    pokemon_id: int
    game_type: str
    guess: str  # name string for game1, number string for game2
    was_challenge: bool = False


class SubmitResponse(BaseModel):
    accuracy: float
    correct_name: str
    correct_number: int
    distance: int | None  # only for number_guess
    games_played: int
    challenge_unlocked: bool


@router.post("/start", response_model=StartResponse)
def start_game(req: StartRequest, db: Session = Depends(get_db)):
    user = _upsert_user(req.username, db)
    games_played = _game_count(user.id, db)
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

    return StartResponse(
        pokemon_id=pokemon.id,
        sprite_url=pokemon.sprite_url,
        name=pokemon.name if req.game_type == "number_guess" else None,
        challenge_unlocked=challenge_unlocked,
        games_played=games_played,
    )


@router.post("/submit", response_model=SubmitResponse)
def submit_answer(req: SubmitRequest, db: Session = Depends(get_db)):
    user = _upsert_user(req.username, db)
    pokemon = db.query(Pokemon).get(req.pokemon_id)
    if not pokemon:
        raise HTTPException(status_code=404, detail="Pokémon not found")

    if req.game_type == "name_guess":
        accuracy = name_accuracy(req.guess, pokemon.name)
        distance = None
    elif req.game_type == "number_guess":
        try:
            guess_num = int(req.guess)
        except ValueError:
            raise HTTPException(status_code=422, detail="guess must be an integer for number_guess")
        distance = abs(guess_num - pokemon.id)
        accuracy = number_accuracy(guess_num, pokemon.id)
    else:
        raise HTTPException(status_code=422, detail="game_type must be name_guess or number_guess")

    result = GameResult(
        user_id=user.id,
        pokemon_id=pokemon.id,
        game_type=req.game_type,
        accuracy=accuracy,
        was_challenge=req.was_challenge,
    )
    db.add(result)
    db.commit()

    games_played = _game_count(user.id, db)
    challenge_unlocked = games_played >= CHALLENGE_THRESHOLD

    # Retrain model every 10 new results once challenge mode is available
    if challenge_unlocked and games_played % 10 == 0:
        xgboost_model.train(user.id, db)

    return SubmitResponse(
        accuracy=round(accuracy, 1),
        correct_name=pokemon.name,
        correct_number=pokemon.id,
        distance=distance,
        games_played=games_played,
        challenge_unlocked=challenge_unlocked,
    )
