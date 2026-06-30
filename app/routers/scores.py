from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import GameResult, User
from app.services.level_system import level_from_xp

router = APIRouter(prefix="/scores", tags=["scores"])


class UserScore(BaseModel):
    username: str
    total_games: int
    avg_score: float
    best_score: float
    worst_score: float


class LeaderboardResponse(BaseModel):
    scores: list[UserScore]


class UserDetailResponse(BaseModel):
    username: str
    scores: list[dict]


@router.get("/games")
def list_game_types(db: Session = Depends(get_db)):
    rows = db.query(GameResult.game_type).distinct().order_by(GameResult.game_type).all()
    return {"game_types": [r[0] for r in rows]}


@router.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(
    game_type: Optional[str] = Query(
        default=None,
        pattern="^(name_easy|name_guess|name_hard|number_guess|type_easy|type_hard)$",
    ),
    db: Session = Depends(get_db),
):
    q = db.query(
        User.username,
        func.count(GameResult.id).label("total_games"),
        func.avg(GameResult.final_score).label("avg_score"),
        func.max(GameResult.final_score).label("best_score"),
        func.min(GameResult.final_score).label("worst_score"),
    ).join(GameResult, GameResult.user_id == User.id).filter(
        GameResult.final_score.isnot(None)
    )

    if game_type:
        q = q.filter(GameResult.game_type == game_type)

    rows = (
        q.group_by(User.id)
        .order_by(func.avg(GameResult.final_score).desc())
        .all()
    )

    scores = [
        UserScore(
            username=row.username,
            total_games=row.total_games,
            avg_score=round(row.avg_score or 0, 1),
            best_score=round(row.best_score or 0, 1),
            worst_score=round(row.worst_score or 0, 1),
        )
        for row in rows
        if row.total_games > 0
    ]

    return LeaderboardResponse(scores=scores)


@router.get("/trainers")
def trainers_leaderboard(db: Session = Depends(get_db)):
    rows = (
        db.query(User)
        .filter(User.total_xp > 0)
        .order_by(User.total_xp.desc())
        .limit(100)
        .all()
    )
    return {
        "trainers": [
            {
                "rank": i + 1,
                "username": u.username,
                "player_level": level_from_xp(u.total_xp),
                "total_xp": round(u.total_xp, 1),
            }
            for i, u in enumerate(rows)
        ]
    }


@router.get("/user/{username}", response_model=UserDetailResponse)
def user_scores(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return UserDetailResponse(username=username, scores=[])

    results = (
        db.query(GameResult)
        .filter(GameResult.user_id == user.id)
        .order_by(GameResult.timestamp.desc())
        .limit(100)
        .all()
    )

    scores = [
        {
            "game_type": r.game_type,
            "accuracy": round(r.accuracy, 1),
            "final_score": round(r.final_score, 1) if r.final_score is not None else None,
            "time_used": round(r.time_used, 1) if r.time_used is not None else None,
            "pokemon_id": r.pokemon_id,
            "was_challenge": r.was_challenge,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in results
    ]
    return UserDetailResponse(username=username, scores=scores)
