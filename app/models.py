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


class GameResult(Base):
    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    pokemon_id: Mapped[int] = mapped_column(Integer, ForeignKey("pokemon.id"), nullable=False)
    game_type: Mapped[str] = mapped_column(String, nullable=False)  # name_guess / number_guess
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    was_challenge: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="results")
    pokemon: Mapped["Pokemon"] = relationship(back_populates="results")
