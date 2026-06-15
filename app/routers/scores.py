from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import GameResult, User

router = APIRouter(prefix="/scores", tags=["scores"])


class UserScore(BaseModel):
    username: str
    total_games: int
    avg_accuracy: float
    best_accuracy: float
    worst_accuracy: float


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
    game_type: Optional[str] = Query(default=None, pattern="^(name_guess|number_guess|type_easy|type_hard)$"),
    db: Session = Depends(get_db),
):
    q = db.query(
        User.username,
        func.count(GameResult.id).label("total_games"),
        func.avg(GameResult.accuracy).label("avg_accuracy"),
        func.max(GameResult.accuracy).label("best_accuracy"),
        func.min(GameResult.accuracy).label("worst_accuracy"),
    ).join(GameResult, GameResult.user_id == User.id)

    if game_type:
        q = q.filter(GameResult.game_type == game_type)

    rows = (
        q.group_by(User.id)
        .order_by(func.avg(GameResult.accuracy).desc())
        .all()
    )

    scores = [
        UserScore(
            username=row.username,
            total_games=row.total_games,
            avg_accuracy=round(row.avg_accuracy or 0, 1),
            best_accuracy=round(row.best_accuracy or 0, 1),
            worst_accuracy=round(row.worst_accuracy or 0, 1),
        )
        for row in rows
        if row.total_games > 0
    ]

    return LeaderboardResponse(scores=scores)


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
            "pokemon_id": r.pokemon_id,
            "was_challenge": r.was_challenge,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in results
    ]
    return UserDetailResponse(username=username, scores=scores)
