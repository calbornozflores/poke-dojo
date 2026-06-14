from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GameResult, User

router = APIRouter(prefix="/scores", tags=["scores"])


class UserScore(BaseModel):
    username: str
    total_games: int
    avg_accuracy: float
    avg_name_accuracy: float | None
    avg_number_accuracy: float | None
    best_accuracy: float
    worst_accuracy: float


class LeaderboardResponse(BaseModel):
    scores: list[UserScore]


class UserDetailResponse(BaseModel):
    username: str
    scores: list[dict]


@router.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(db: Session = Depends(get_db)):
    rows = (
        db.query(
            User.username,
            func.count(GameResult.id).label("total_games"),
            func.avg(GameResult.accuracy).label("avg_accuracy"),
            func.max(GameResult.accuracy).label("best_accuracy"),
            func.min(GameResult.accuracy).label("worst_accuracy"),
        )
        .join(GameResult, GameResult.user_id == User.id)
        .group_by(User.id)
        .order_by(func.avg(GameResult.accuracy).desc())
        .all()
    )

    scores = []
    for row in rows:
        # Per-game-type averages
        name_avg = (
            db.query(func.avg(GameResult.accuracy))
            .join(User, User.id == GameResult.user_id)
            .filter(User.username == row.username, GameResult.game_type == "name_guess")
            .scalar()
        )
        num_avg = (
            db.query(func.avg(GameResult.accuracy))
            .join(User, User.id == GameResult.user_id)
            .filter(User.username == row.username, GameResult.game_type == "number_guess")
            .scalar()
        )
        scores.append(
            UserScore(
                username=row.username,
                total_games=row.total_games,
                avg_accuracy=round(row.avg_accuracy or 0, 1),
                avg_name_accuracy=round(name_avg, 1) if name_avg is not None else None,
                avg_number_accuracy=round(num_avg, 1) if num_avg is not None else None,
                best_accuracy=round(row.best_accuracy or 0, 1),
                worst_accuracy=round(row.worst_accuracy or 0, 1),
            )
        )

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
