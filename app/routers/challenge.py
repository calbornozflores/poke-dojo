from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GameResult, User
from app.services import xgboost_model

router = APIRouter(prefix="/challenge", tags=["challenge"])

CHALLENGE_THRESHOLD = 20


class UnlockStatus(BaseModel):
    unlocked: bool
    games_played: int
    games_needed: int


class TrainResponse(BaseModel):
    success: bool
    message: str


@router.get("/status/{username}", response_model=UnlockStatus)
def challenge_status(
    username: str,
    game_type: str = Query(default="name_guess", pattern="^(name_guess|number_guess)$"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return UnlockStatus(unlocked=False, games_played=0, games_needed=CHALLENGE_THRESHOLD)

    games_played = (
        db.query(GameResult)
        .filter(GameResult.user_id == user.id, GameResult.game_type == game_type)
        .count()
    )
    return UnlockStatus(
        unlocked=games_played >= CHALLENGE_THRESHOLD,
        games_played=games_played,
        games_needed=max(0, CHALLENGE_THRESHOLD - games_played),
    )


@router.post("/train/{username}", response_model=TrainResponse)
def train_model(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return TrainResponse(success=False, message="User not found")

    games_played = db.query(GameResult).filter(GameResult.user_id == user.id).count()
    if games_played < CHALLENGE_THRESHOLD:
        return TrainResponse(
            success=False,
            message=f"Need {CHALLENGE_THRESHOLD - games_played} more games to unlock challenge mode",
        )

    success = xgboost_model.train(user.id, game_type, db)
    if success:
        return TrainResponse(success=True, message="Challenge model trained successfully")
    return TrainResponse(success=False, message="Not enough data to train model")
