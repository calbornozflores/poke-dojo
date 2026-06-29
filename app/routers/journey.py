from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User, EvoScoreHistory
from app.services.level_system import level_from_xp, xp_progress_in_current_level

router = APIRouter(prefix="/journey", tags=["journey"])


@router.get("/history")
def journey_history(
    username: str = Query(...),
    game_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {
            "has_data": False, "current_score": 0, "history": [],
            "player_level": 1, "total_xp": 0.0, "xp_current": 0.0,
            "xp_needed": round(1.25 * (2 ** 3) - 1.25 * (1 ** 3), 1),
        }

    _COMBINED_TYPES = ("name_it", "number_guess", "guess_type")

    q = db.query(EvoScoreHistory).filter(EvoScoreHistory.user_id == user.id)
    if game_type:
        q = q.filter(EvoScoreHistory.game_type == game_type)
    else:
        q = q.filter(EvoScoreHistory.game_type.in_(_COMBINED_TYPES))
    history = q.order_by(EvoScoreHistory.timestamp.asc()).all()

    player_level = level_from_xp(user.total_xp)
    xp_current, xp_needed = xp_progress_in_current_level(user.total_xp)

    return {
        "has_data": len(history) > 0,
        "current_score": round(history[-1].evo_score, 1) if history else 0,
        "history": [
            {
                "evo_score": h.evo_score,
                "final_score": h.final_score,
                "game_type": h.game_type,
                "timestamp": h.timestamp.isoformat(),
            }
            for h in history
        ],
        "player_level": player_level,
        "total_xp": round(user.total_xp, 1),
        "xp_current": xp_current,
        "xp_needed": xp_needed,
    }
