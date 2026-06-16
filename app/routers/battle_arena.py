import random
import math
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import Pokemon, User, CompetitiveMatch, CompetitiveResult

router = APIRouter(prefix="/battle", tags=["battle"])

REVEAL_DURATION = 10  # seconds for silhouette reveal


def _get_or_create_user(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _pick_options(correct: Pokemon, db: Session) -> list[dict]:
    """Return 3 shuffled name options: correct + 2 wrong from same generation."""
    wrong_pool = (
        db.query(Pokemon)
        .filter(Pokemon.generation == correct.generation, Pokemon.id != correct.id)
        .order_by(func.random())
        .limit(2)
        .all()
    )
    # Fallback: pick from any gen if same-gen pool is too small
    if len(wrong_pool) < 2:
        wrong_pool = (
            db.query(Pokemon)
            .filter(Pokemon.id != correct.id)
            .order_by(func.random())
            .limit(2)
            .all()
        )
    names = [correct.name] + [p.name for p in wrong_pool]
    random.shuffle(names)
    correct_pos = names.index(correct.name) + 1  # 1-indexed
    return names, correct_pos


# ── Match lifecycle ──────────────────────────────────────────────────────────

class StartMatchRequest(BaseModel):
    mode: str           # "vs" | "single"
    player1: str
    player2: str | None = None
    rounds: int = 5


class StartMatchResponse(BaseModel):
    match_id: int
    mode: str
    player1: str
    player2: str | None


@router.post("/match/start", response_model=StartMatchResponse)
def start_match(req: StartMatchRequest, db: Session = Depends(get_db)):
    if req.mode not in ("vs", "single"):
        raise HTTPException(400, "mode must be 'vs' or 'single'")
    if req.mode == "vs" and not req.player2:
        raise HTTPException(400, "player2 required for VS mode")

    _get_or_create_user(req.player1, db)
    if req.player2:
        _get_or_create_user(req.player2, db)

    match = CompetitiveMatch(
        mode=req.mode,
        player1=req.player1,
        player2=req.player2,
        rounds=req.rounds,
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return StartMatchResponse(
        match_id=match.id,
        mode=match.mode,
        player1=match.player1,
        player2=match.player2,
    )


# ── Round ────────────────────────────────────────────────────────────────────

class RoundData(BaseModel):
    match_id: int
    round_number: int
    pokemon_id: int
    sprite_url: str
    options: list[str]       # 3 names in display order
    correct_position: int    # 1/2/3
    generation: int
    reveal_duration: int     # seconds


@router.get("/round/next", response_model=RoundData)
def next_round(match_id: int, round_number: int, db: Session = Depends(get_db)):
    match = db.get(CompetitiveMatch, match_id)
    if not match:
        raise HTTPException(404, "Match not found")

    # Avoid re-using Pokémon already seen this match
    used_ids = {r.pokemon_id for r in match.competitive_results}
    query = db.query(Pokemon)
    if used_ids:
        query = query.filter(~Pokemon.id.in_(used_ids))
    pokemon = query.order_by(func.random()).first()
    if not pokemon:
        raise HTTPException(404, "No Pokémon available")

    options, correct_pos = _pick_options(pokemon, db)
    return RoundData(
        match_id=match_id,
        round_number=round_number,
        pokemon_id=pokemon.id,
        sprite_url=pokemon.sprite_url,
        options=options,
        correct_position=correct_pos,
        generation=pokemon.generation,
        reveal_duration=REVEAL_DURATION,
    )


# ── Submit round ─────────────────────────────────────────────────────────────

class SubmitRoundRequest(BaseModel):
    match_id: int
    round_number: int
    pokemon_id: int
    correct_option_position: int
    player1_key_pressed: int | None = None
    player1_response_ms: int | None = None
    player2_key_pressed: int | None = None
    player2_response_ms: int | None = None


class RoundResult(BaseModel):
    player1_was_correct: bool
    player1_score: int
    player2_was_correct: bool | None
    player2_score: int | None
    correct_position: int
    pokemon_name: str
    sprite_url: str


@router.post("/round/submit", response_model=RoundResult)
def submit_round(req: SubmitRoundRequest, db: Session = Depends(get_db)):
    match = db.get(CompetitiveMatch, req.match_id)
    if not match:
        raise HTTPException(404, "Match not found")

    pokemon = db.get(Pokemon, req.pokemon_id)
    if not pokemon:
        raise HTTPException(404, "Pokémon not found")

    def calc_score(key_pressed, response_ms):
        if key_pressed is None or response_ms is None:
            return False, 0
        correct = key_pressed == req.correct_option_position
        if not correct:
            return False, 0
        # score = max(0, floor(time_remaining/reveal_duration * 100))
        time_remaining = max(0, REVEAL_DURATION * 1000 - response_ms) / 1000
        score = max(0, math.floor(time_remaining / REVEAL_DURATION * 100))
        return True, score

    p1_correct, p1_score = calc_score(req.player1_key_pressed, req.player1_response_ms)
    p2_correct, p2_score = calc_score(req.player2_key_pressed, req.player2_response_ms)

    result = CompetitiveResult(
        match_id=req.match_id,
        round_number=req.round_number,
        pokemon_id=req.pokemon_id,
        correct_option_position=req.correct_option_position,
        player1_key_pressed=req.player1_key_pressed,
        player1_response_ms=req.player1_response_ms,
        player1_was_correct=p1_correct,
        player1_score=p1_score,
        player2_key_pressed=req.player2_key_pressed,
        player2_response_ms=req.player2_response_ms,
        player2_was_correct=p2_correct,
        player2_score=p2_score,
    )
    db.add(result)
    db.commit()

    return RoundResult(
        player1_was_correct=p1_correct,
        player1_score=p1_score,
        player2_was_correct=p2_correct if match.mode == "vs" else None,
        player2_score=p2_score if match.mode == "vs" else None,
        correct_position=req.correct_option_position,
        pokemon_name=pokemon.name,
        sprite_url=pokemon.sprite_url,
    )


# ── Finish match ─────────────────────────────────────────────────────────────

class FinishMatchRequest(BaseModel):
    match_id: int


class MatchSummary(BaseModel):
    match_id: int
    mode: str
    player1: str
    player2: str | None
    winner: str | None
    player1_total: int
    player2_total: int | None
    rounds: list[dict]


@router.post("/match/finish", response_model=MatchSummary)
def finish_match(req: FinishMatchRequest, db: Session = Depends(get_db)):
    match = db.get(CompetitiveMatch, req.match_id)
    if not match:
        raise HTTPException(404, "Match not found")

    results = (
        db.query(CompetitiveResult)
        .filter(CompetitiveResult.match_id == req.match_id)
        .order_by(CompetitiveResult.round_number)
        .all()
    )

    p1_total = sum(r.player1_score for r in results)
    p2_total = sum(r.player2_score for r in results) if match.mode == "vs" else None

    if match.mode == "vs" and p2_total is not None:
        if p1_total > p2_total:
            winner = match.player1
        elif p2_total > p1_total:
            winner = match.player2
        else:
            winner = "draw"
    else:
        winner = match.player1  # single player always "wins" the run

    match.winner = winner
    match.rounds = len(results)
    db.commit()

    round_data = []
    for r in results:
        p = db.get(Pokemon, r.pokemon_id)
        round_data.append({
            "round_number": r.round_number,
            "pokemon_id": r.pokemon_id,
            "pokemon_name": p.name if p else "?",
            "sprite_url": p.sprite_url if p else "",
            "correct_position": r.correct_option_position,
            "player1_key": r.player1_key_pressed,
            "player1_ms": r.player1_response_ms,
            "player1_correct": r.player1_was_correct,
            "player1_score": r.player1_score,
            "player2_key": r.player2_key_pressed,
            "player2_ms": r.player2_response_ms,
            "player2_correct": r.player2_was_correct,
            "player2_score": r.player2_score,
        })

    return MatchSummary(
        match_id=match.id,
        mode=match.mode,
        player1=match.player1,
        player2=match.player2,
        winner=winner,
        player1_total=p1_total,
        player2_total=p2_total,
        rounds=round_data,
    )


# ── Leaderboard ──────────────────────────────────────────────────────────────

class ArenaLeaderEntry(BaseModel):
    username: str
    best_run_score: int
    longest_streak: int
    best_vs_score: int
    vs_win_rate: float | None
    vs_matches: int


@router.get("/leaderboard", response_model=list[ArenaLeaderEntry])
def arena_leaderboard(db: Session = Depends(get_db)):
    # Best single-player run score (max total from a single match)
    single_matches = (
        db.query(CompetitiveMatch)
        .filter(CompetitiveMatch.mode == "single")
        .all()
    )
    vs_matches = (
        db.query(CompetitiveMatch)
        .filter(CompetitiveMatch.mode == "vs")
        .all()
    )

    player_stats: dict[str, dict] = {}

    def ensure(name):
        if name not in player_stats:
            player_stats[name] = {
                "best_run_score": 0,
                "longest_streak": 0,
                "best_vs_score": 0,
                "vs_wins": 0,
                "vs_total": 0,
            }

    for m in single_matches:
        ensure(m.player1)
        results = db.query(CompetitiveResult).filter(CompetitiveResult.match_id == m.id).all()
        total = sum(r.player1_score for r in results)
        if total > player_stats[m.player1]["best_run_score"]:
            player_stats[m.player1]["best_run_score"] = total
        # Longest streak: consecutive correct answers
        streak = max_streak = cur = 0
        for r in sorted(results, key=lambda x: x.round_number):
            if r.player1_was_correct:
                cur += 1
                max_streak = max(max_streak, cur)
            else:
                cur = 0
        if max_streak > player_stats[m.player1]["longest_streak"]:
            player_stats[m.player1]["longest_streak"] = max_streak

    for m in vs_matches:
        for pname in [m.player1, m.player2]:
            if not pname:
                continue
            ensure(pname)
            results = db.query(CompetitiveResult).filter(CompetitiveResult.match_id == m.id).all()
            if pname == m.player1:
                score = sum(r.player1_score for r in results)
            else:
                score = sum(r.player2_score for r in results)
            if score > player_stats[pname]["best_vs_score"]:
                player_stats[pname]["best_vs_score"] = score
            player_stats[pname]["vs_total"] += 1
            if m.winner == pname:
                player_stats[pname]["vs_wins"] += 1

    entries = []
    for name, s in player_stats.items():
        vs_rate = None
        if s["vs_total"] >= 5:
            vs_rate = round(s["vs_wins"] / s["vs_total"] * 100, 1)
        entries.append(ArenaLeaderEntry(
            username=name,
            best_run_score=s["best_run_score"],
            longest_streak=s["longest_streak"],
            best_vs_score=s["best_vs_score"],
            vs_win_rate=vs_rate,
            vs_matches=s["vs_total"],
        ))

    entries.sort(key=lambda e: e.best_run_score, reverse=True)
    return entries
