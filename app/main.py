import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Must run before any service that reads env vars

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
import logging

logger = logging.getLogger(__name__)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import engine, run_migrations
from app.models import Base
from app.routers import game, scores, challenge, journey, battle_arena, auth, daily_challenge
from app.services import supabase_client
from app.services.data_loader import (
    check_db_ready,
    fetch_all_pokemon_background,
    get_progress,
    _state as loader_state,
)

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="poke-dojo")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

ROOT = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Inject Supabase config as template globals so every page can check availability
templates.env.globals["supabase_configured"] = supabase_client.is_configured()
templates.env.globals["supabase_url"] = supabase_client._url()
templates.env.globals["supabase_anon_key"] = supabase_client._anon_key()

app.include_router(game.router)
app.include_router(scores.router)
app.include_router(challenge.router)
app.include_router(journey.router)
app.include_router(battle_arena.router)
app.include_router(auth.router)
app.include_router(daily_challenge.router)


@app.on_event("startup")
async def startup() -> None:
    if check_db_ready():
        loader_state["done"] = True
        loader_state["needed"] = False
        loader_state["fetched"] = loader_state["total"]
    else:
        loader_state["needed"] = True
        asyncio.create_task(fetch_all_pokemon_background())


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    progress = get_progress()
    # First-time startup: send to loading screen
    if progress["needed"] and not progress["done"]:
        return RedirectResponse("/loading")
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/loading")
async def loading(request: Request):
    # If already ready, skip straight to home
    progress = get_progress()
    if progress["done"] and not progress["needed"]:
        return RedirectResponse("/")
    return templates.TemplateResponse(request=request, name="loading.html")


@app.get("/play")
async def play(request: Request):
    return templates.TemplateResponse(request=request, name="game.html")


@app.get("/leaderboard")
async def leaderboard(request: Request):
    return templates.TemplateResponse(request=request, name="scores.html")


@app.get("/profile")
async def profile(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")


@app.get("/journey")
async def trainer_journey(request: Request):
    return templates.TemplateResponse(request=request, name="trainer_journey.html")


@app.get("/battle-arena")
async def battle_arena_page(request: Request):
    return templates.TemplateResponse(request=request, name="battle_arena.html")


@app.get("/arena-leaderboard")
async def arena_leaderboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="arena_leaderboard.html")


@app.get("/daily-challenge")
async def daily_challenge_page(request: Request):
    return templates.TemplateResponse(request=request, name="daily_challenge.html")


@app.get("/faq")
async def faq_page(request: Request):
    return templates.TemplateResponse(request=request, name="faq.html")


@app.get("/contact")
async def contact_page(request: Request):
    return templates.TemplateResponse(request=request, name="contact.html")


@app.get("/auth/callback")
async def auth_callback_page(request: Request):
    return templates.TemplateResponse(request=request, name="auth_callback.html")


@app.get("/auth/claim")
async def auth_claim_page(request: Request):
    return templates.TemplateResponse(request=request, name="auth_claim.html")


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status() -> JSONResponse:
    p = get_progress()
    pct = int((p["fetched"] / p["total"]) * 100) if p["total"] else 0
    return JSONResponse({
        "ready": p["done"],
        "fetched": p["fetched"],
        "total": p["total"],
        "percent": pct,
    })
