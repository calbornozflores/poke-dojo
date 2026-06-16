from datetime import datetime
from sqlalchemy import Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Pokemon(Base):
    __tablename__ = "pokemon"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # pokedex number
    name: Mapped[str] = mapped_column(String, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)  # basic / stage_1 / stage_2
    sprite_url: Mapped[str] = mapped_column(String, nullable=False)
    type1: Mapped[str] = mapped_column(String, nullable=False)
    type2: Mapped[str] = mapped_column(String, nullable=True)
    hp: Mapped[int] = mapped_column(Integer, nullable=False)
    attack: Mapped[int] = mapped_column(Integer, nullable=False)
    defense: Mapped[int] = mapped_column(Integer, nullable=False)
    sp_attack: Mapped[int] = mapped_column(Integer, nullable=False)
    sp_defense: Mapped[int] = mapped_column(Integer, nullable=False)
    speed: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    weight: Mapped[int] = mapped_column(Integer, nullable=True, default=0)

    results: Mapped[list["GameResult"]] = relationship(back_populates="pokemon")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    results: Mapped[list["GameResult"]] = relationship(back_populates="user")
    evo_history: Mapped[list["EvoScoreHistory"]] = relationship(back_populates="user")


class GameResult(Base):
    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    pokemon_id: Mapped[int] = mapped_column(Integer, ForeignKey("pokemon.id"), nullable=False)
    game_type: Mapped[str] = mapped_column(String, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    time_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    was_challenge: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="results")
    pokemon: Mapped["Pokemon"] = relationship(back_populates="results")


class EvoScoreHistory(Base):
    __tablename__ = "evo_score_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    game_type: Mapped[str] = mapped_column(String, nullable=False)
    evo_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="evo_history")


class CompetitiveMatch(Base):
    __tablename__ = "competitive_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)       # "vs" | "single"
    player1: Mapped[str] = mapped_column(String, nullable=False)
    player2: Mapped[str | None] = mapped_column(String, nullable=True)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    competitive_results: Mapped[list["CompetitiveResult"]] = relationship(back_populates="match")


class CompetitiveResult(Base):
    __tablename__ = "competitive_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitive_matches.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pokemon_id: Mapped[int] = mapped_column(Integer, ForeignKey("pokemon.id"), nullable=False)
    correct_option_position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1/2/3
    player1_key_pressed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player1_response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player1_was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    player1_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    player2_key_pressed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player2_response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player2_was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    player2_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    match: Mapped["CompetitiveMatch"] = relationship(back_populates="competitive_results")
