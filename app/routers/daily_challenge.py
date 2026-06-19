from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from rapidfuzz import fuzz

from app.database import get_db
from app.models import Pokemon, DailyPokemon, DailyChallengeResult, DailyChallengeGuess

router = APIRouter(prefix="/daily", tags=["daily"])

EPOCH = date(2026, 1, 1)
TOTAL_POKEMON = 1025


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_create_daily(today: date, db: Session) -> int:
    record = db.get(DailyPokemon, today)
    if record:
        return record.pokemon_id
    pokemon_id = ((today - EPOCH).days % TOTAL_POKEMON) + 1
    try:
        db.add(DailyPokemon(date=today, pokemon_id=pokemon_id))
        db.commit()
    except Exception:
        db.rollback()
        record = db.get(DailyPokemon, today)
        return record.pokemon_id
    return pokemon_id


def _compute_distance(guess: Pokemon, answer: Pokemon) -> float:
    word_match = fuzz.ratio(guess.name.lower(), answer.name.lower()) / 100.0
    pokedex_proximity = (TOTAL_POKEMON - abs(guess.id - answer.id)) / TOTAL_POKEMON
    return round(1.0 - (0.5 * word_match + 0.5 * pokedex_proximity), 4)


# ── Schemas ───────────────────────────────────────────────────────────────────

class TodayResponse(BaseModel):
    date: str
    player_count: int


class GuessRequest(BaseModel):
    username: str
    guess_pokemon_id: int


class GuessResponse(BaseModel):
    distance: float
    is_correct: bool
    guess_number: int
    answer_pokemon_id: int | None = None


class StatusResponse(BaseModel):
    played: bool
    guesses: int
    solved: bool
    best_distance: float
    answer_pokemon_id: int | None = None


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    guesses: int
    solved: bool
    timestamp: str


class SearchResult(BaseModel):
    id: int
    name: str
    sprite_url: str
    type1: str
    type2: str | None
    generation: int


class GuessHistoryItem(BaseModel):
    guess_number: int
    pokemon_id: int
    name: str
    sprite_url: str
    type1: str
    type2: str | None
    generation: int
    distance: float
    is_correct: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/today", response_model=TodayResponse)
def today_info(db: Session = Depends(get_db)):
    today = date.today()
    _get_or_create_daily(today, db)
    count = (
        db.query(DailyChallengeResult)
        .filter(DailyChallengeResult.date == today)
        .count()
    )
    return TodayResponse(date=today.isoformat(), player_count=count)


@router.post("/guess", response_model=GuessResponse)
def submit_guess(req: GuessRequest, db: Session = Depends(get_db)):
    today = date.today()
    answer_id = _get_or_create_daily(today, db)
    answer = db.get(Pokemon, answer_id)
    if not answer:
        raise HTTPException(status_code=500, detail="Daily Pokémon not found in database")

    guess_pokemon = db.get(Pokemon, req.guess_pokemon_id)
    if not guess_pokemon:
        raise HTTPException(status_code=404, detail="Pokémon not found")

    # Block already-solved sessions
    solved_row = (
        db.query(DailyChallengeResult)
        .filter(
            DailyChallengeResult.username == req.username,
            DailyChallengeResult.date == today,
            DailyChallengeResult.solved == True,
        )
        .first()
    )
    if solved_row:
        raise HTTPException(status_code=409, detail="Already solved today's challenge")

    # Block duplicate guesses
    duplicate = (
        db.query(DailyChallengeGuess)
        .filter(
            DailyChallengeGuess.username == req.username,
            DailyChallengeGuess.date == today,
            DailyChallengeGuess.pokemon_id == req.guess_pokemon_id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="Already guessed this Pokémon today")

    prior_count = (
        db.query(DailyChallengeGuess)
        .filter(
            DailyChallengeGuess.username == req.username,
            DailyChallengeGuess.date == today,
        )
        .count()
    )
    guess_number = prior_count + 1
    distance = _compute_distance(guess_pokemon, answer)
    is_correct = req.guess_pokemon_id == answer_id

    db.add(DailyChallengeGuess(
        username=req.username,
        date=today,
        guess_number=guess_number,
        pokemon_id=req.guess_pokemon_id,
        distance=distance,
    ))

    result_row = (
        db.query(DailyChallengeResult)
        .filter(
            DailyChallengeResult.username == req.username,
            DailyChallengeResult.date == today,
        )
        .first()
    )
    if result_row:
        result_row.guesses = guess_number
        result_row.solved = is_correct
        if distance < result_row.best_distance:
            result_row.best_distance = distance
    else:
        db.add(DailyChallengeResult(
            username=req.username,
            date=today,
            guesses=guess_number,
            solved=is_correct,
            best_distance=distance,
        ))

    db.commit()

    return GuessResponse(
        distance=distance,
        is_correct=is_correct,
        guess_number=guess_number,
        answer_pokemon_id=answer_id if is_correct else None,
    )


@router.get("/status", response_model=StatusResponse)
def get_status(username: str = Query(...), db: Session = Depends(get_db)):
    today = date.today()
    answer_id = _get_or_create_daily(today, db)

    result_row = (
        db.query(DailyChallengeResult)
        .filter(
            DailyChallengeResult.username == username,
            DailyChallengeResult.date == today,
        )
        .first()
    )
    if not result_row:
        return StatusResponse(played=False, guesses=0, solved=False, best_distance=1.0)

    return StatusResponse(
        played=True,
        guesses=result_row.guesses,
        solved=result_row.solved,
        best_distance=result_row.best_distance,
        answer_pokemon_id=answer_id if result_row.solved else None,
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
def daily_leaderboard(
    date_str: str = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
):
    target = date.fromisoformat(date_str) if date_str else date.today()
    rows = (
        db.query(DailyChallengeResult)
        .filter(DailyChallengeResult.date == target)
        .all()
    )
    rows.sort(key=lambda r: (0 if r.solved else 1, r.guesses))
    return [
        LeaderboardEntry(
            rank=i + 1,
            username=r.username,
            guesses=r.guesses,
            solved=r.solved,
            timestamp=r.timestamp.isoformat(),
        )
        for i, r in enumerate(rows)
    ]


@router.get("/search", response_model=list[SearchResult])
def search_pokemon(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    prefix = (
        db.query(Pokemon)
        .filter(Pokemon.name.ilike(f"{q}%"))
        .order_by(Pokemon.name)
        .limit(8)
        .all()
    )
    results = list(prefix)
    if len(results) < 4:
        extra_ids = [p.id for p in results]
        extra = (
            db.query(Pokemon)
            .filter(Pokemon.name.ilike(f"%{q}%"), ~Pokemon.id.in_(extra_ids))
            .order_by(Pokemon.name)
            .limit(8 - len(results))
            .all()
        )
        results = results + extra

    return [
        SearchResult(
            id=p.id,
            name=p.name,
            sprite_url=p.sprite_url,
            type1=p.type1,
            type2=p.type2,
            generation=p.generation,
        )
        for p in results
    ]


@router.get("/guesses", response_model=list[GuessHistoryItem])
def get_guesses(username: str = Query(...), db: Session = Depends(get_db)):
    today = date.today()
    rows = (
        db.query(DailyChallengeGuess, Pokemon)
        .join(Pokemon, DailyChallengeGuess.pokemon_id == Pokemon.id)
        .filter(
            DailyChallengeGuess.username == username,
            DailyChallengeGuess.date == today,
        )
        .order_by(DailyChallengeGuess.guess_number)
        .all()
    )
    return [
        GuessHistoryItem(
            guess_number=g.guess_number,
            pokemon_id=p.id,
            name=p.name,
            sprite_url=p.sprite_url,
            type1=p.type1,
            type2=p.type2,
            generation=p.generation,
            distance=g.distance,
            is_correct=(g.distance == 0.0),
        )
        for g, p in rows
    ]
