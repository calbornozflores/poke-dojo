"""
Retake all README screenshots with proper image-load waits.
Run with: uv run python take_screenshots.py
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
OUT = Path("screenshots")
OUT.mkdir(exist_ok=True)

USERNAME = "Claudio"

WAIT_DOJO_SPRITE = """
() => {
  const img = document.getElementById('pokemon-sprite');
  return img && img.complete && img.naturalWidth > 0 && !!img.src && img.src !== window.location.href;
}
"""

WAIT_ARENA_SPRITE = """
() => {
  const img = document.getElementById('arena-sprite');
  return img && img.complete && img.naturalWidth > 0 && !!img.src && img.src !== window.location.href;
}
"""

WAIT_TYPES = """
() => {
  const c = document.getElementById('type-choices');
  if (!c || c.children.length === 0) return false;
  // also wait for type badge images
  const imgs = c.querySelectorAll('img');
  return imgs.length === 0 || Array.from(imgs).every(i => i.complete);
}
"""

async def new_page(browser, width=1280, height=800):
    ctx = await browser.new_context(viewport={"width": width, "height": height})
    page = await ctx.new_page()
    await page.add_init_script(f"localStorage.setItem('poke_username', '{USERNAME}');")
    return page

async def take(page, name):
    path = str(OUT / name)
    await page.screenshot(path=path, full_page=False)
    print(f"  ✓ {name}")

async def dojo_start_game(page, mode_btn_selector):
    """Click mode, wait for intro, return."""
    await page.click(mode_btn_selector)
    await page.wait_for_selector("#intro-screen:not(.hidden)", timeout=5000)
    await page.wait_for_timeout(300)

async def dojo_click_start(page):
    await page.click("#intro-start-btn")
    await page.wait_for_selector("#game-screen:not(.hidden)", timeout=5000)

async def wait_dojo_sprite(page):
    await page.wait_for_function(WAIT_DOJO_SPRITE, timeout=15000)
    await page.wait_for_timeout(300)

async def wait_arena_sprite(page):
    await page.wait_for_function(WAIT_ARENA_SPRITE, timeout=15000)
    await page.wait_for_timeout(400)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # ── 01 Home ──────────────────────────────────────────────────────────
        print("01 Home")
        page = await new_page(browser)
        await page.goto(BASE)
        await page.wait_for_load_state("networkidle")
        await take(page, "01_home.png")
        await page.close()

        # ── 02 Play intro (Name It selected) ─────────────────────────────────
        print("02 Play intro")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-game1", timeout=5000)
        await dojo_start_game(page, "#btn-game1")
        await take(page, "02_play_intro.png")
        await page.close()

        # ── 03 Name It Medium ────────────────────────────────────────────────
        print("03 Name It Medium")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-game1", timeout=5000)
        await dojo_start_game(page, "#btn-game1")
        await dojo_click_start(page)
        await wait_dojo_sprite(page)
        await take(page, "03_play_nameit.png")
        await page.close()

        # ── 04 Name It Hard intro ─────────────────────────────────────────────
        print("04 Name It Hard intro")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-game1", timeout=5000)
        await page.click("#btn-game1")
        await page.wait_for_selector("#name-submode:not(.hidden)", timeout=5000)
        await page.click("#submode-name-hard")
        await page.wait_for_selector("#intro-screen:not(.hidden)", timeout=5000)
        await page.wait_for_timeout(300)
        await take(page, "04_play_nameit_hard_intro.png")
        await page.close()

        # ── 05 Name It Hard game ──────────────────────────────────────────────
        print("05 Name It Hard")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-game1", timeout=5000)
        await page.click("#btn-game1")
        await page.wait_for_selector("#name-submode:not(.hidden)", timeout=5000)
        await page.click("#submode-name-hard")
        await page.wait_for_selector("#intro-screen:not(.hidden)", timeout=5000)
        await dojo_click_start(page)
        await wait_dojo_sprite(page)
        await take(page, "05_play_nameit_hard.png")
        await page.close()

        # ── 06 Result screen ─────────────────────────────────────────────────
        print("06 Result")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-game1", timeout=5000)
        await dojo_start_game(page, "#btn-game1")
        await dojo_click_start(page)
        await wait_dojo_sprite(page)
        await page.fill("#name-input", "Pikachu")
        await page.click("#submit-btn")
        await page.wait_for_selector("#result-zone:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(600)
        await take(page, "06_play_result.png")
        await page.close()

        # ── 07 Guess Number intro ─────────────────────────────────────────────
        print("07 Guess Number intro")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-game2", timeout=5000)
        await dojo_start_game(page, "#btn-game2")
        await take(page, "07_play_guessnumber_intro.png")
        await page.close()

        # ── 08 Guess Number game ──────────────────────────────────────────────
        print("08 Guess Number")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-game2", timeout=5000)
        await dojo_start_game(page, "#btn-game2")
        await dojo_click_start(page)
        await wait_dojo_sprite(page)
        await take(page, "08_play_guessnumber.png")
        await page.close()

        # ── 09 Type Easy intro ────────────────────────────────────────────────
        print("09 Type Easy intro")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-type", timeout=5000)
        await dojo_start_game(page, "#btn-type")
        await take(page, "09_play_typeeasy_intro.png")
        await page.close()

        # ── 10 Type Easy game ─────────────────────────────────────────────────
        print("10 Type Easy")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-type", timeout=5000)
        await dojo_start_game(page, "#btn-type")
        await dojo_click_start(page)
        await wait_dojo_sprite(page)
        await page.wait_for_function(WAIT_TYPES, timeout=10000)
        await page.wait_for_timeout(600)
        await take(page, "10_play_typeeasy.png")
        await page.close()

        # ── 11 Type Hard game ─────────────────────────────────────────────────
        print("11 Type Hard")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-type", timeout=5000)
        await page.click("#btn-type")
        await page.wait_for_selector("#type-submode:not(.hidden)", timeout=5000)
        await page.click("#submode-hard")
        await page.wait_for_selector("#intro-screen:not(.hidden)", timeout=5000)
        await dojo_click_start(page)
        await wait_dojo_sprite(page)
        # Type Hard uses #type-hard-area / #type-grid, not #type-choices
        await page.wait_for_selector("#type-hard-area:not(.hidden)", timeout=10000)
        await page.wait_for_function(
            "() => document.getElementById('type-grid') && document.getElementById('type-grid').children.length > 0",
            timeout=10000
        )
        await page.wait_for_timeout(600)
        await take(page, "11_play_typehard.png")
        await page.close()

        # ── 12 Leaderboard ────────────────────────────────────────────────────
        print("12 Leaderboard")
        page = await new_page(browser)
        await page.goto(f"{BASE}/leaderboard")
        await page.wait_for_selector("#global-table:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(500)
        await take(page, "12_leaderboard.png")
        await page.close()

        # ── 13 Profile ────────────────────────────────────────────────────────
        print("13 Profile")
        page = await new_page(browser)
        await page.goto(f"{BASE}/profile")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)
        await take(page, "13_profile.png")
        await page.close()

        # ── 14 Trainer Journey ────────────────────────────────────────────────
        print("14 Trainer Journey")
        page = await new_page(browser)
        await page.goto(f"{BASE}/journey")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)
        await take(page, "14_trainer_journey.png")
        await page.close()

        # ── 15 VS Mode Setup ──────────────────────────────────────────────────
        print("15 VS Mode Setup")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=vs")
        await page.wait_for_selector("#setup-vs:not(.hidden)", timeout=8000)
        await page.fill("#p2-name", "Gary")
        await page.wait_for_timeout(400)
        await take(page, "15_battle_arena_vs_setup.png")
        await page.close()

        # ── 16 Solo Setup ─────────────────────────────────────────────────────
        print("16 Solo Setup")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=single")
        await page.wait_for_selector("#setup-single:not(.hidden)", timeout=8000)
        # Assign keys A/S/D (slot 0 is auto-activated)
        await page.keyboard.press("a")
        await page.keyboard.press("s")
        await page.keyboard.press("d")
        await page.wait_for_timeout(400)
        await take(page, "16_battle_arena_solo_setup.png")
        await page.close()

        # ── 17 VS Round ───────────────────────────────────────────────────────
        print("17 VS Round")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=vs")
        await page.wait_for_selector("#setup-vs:not(.hidden)", timeout=8000)
        await page.fill("#p2-name", "Gary")
        await page.click("#start-match-btn")
        await page.wait_for_selector("#round-screen:not(.hidden)", timeout=10000)
        await wait_arena_sprite(page)
        await take(page, "17_battle_arena_vs_round.png")
        await page.close()

        # ── 18 VS Round Result ────────────────────────────────────────────────
        print("18 VS Round Result")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=vs")
        await page.wait_for_selector("#setup-vs:not(.hidden)", timeout=8000)
        await page.fill("#p2-name", "Gary")
        await page.click("#start-match-btn")
        await page.wait_for_selector("#round-screen:not(.hidden)", timeout=10000)
        await wait_arena_sprite(page)
        # Both players must answer — press Q (P1 option 1) then I (P2 option 1)
        await page.keyboard.press("q")
        await page.wait_for_timeout(200)
        await page.keyboard.press("i")
        await page.wait_for_selector("#round-result-screen:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(600)
        await take(page, "18_battle_arena_vs_result.png")
        await page.close()

        # ── 19 Solo Round ─────────────────────────────────────────────────────
        print("19 Solo Round")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=single")
        await page.wait_for_selector("#setup-single:not(.hidden)", timeout=8000)
        await page.keyboard.press("a")
        await page.keyboard.press("s")
        await page.keyboard.press("d")
        await page.click("#start-match-btn")
        await page.wait_for_selector("#round-screen:not(.hidden)", timeout=10000)
        await wait_arena_sprite(page)
        await take(page, "19_battle_arena_solo_round.png")
        await page.close()

        # ── 20 Match End (VS) ─────────────────────────────────────────────────
        print("20 Match End (VS — 3 rounds)")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=vs")
        await page.wait_for_selector("#setup-vs:not(.hidden)", timeout=8000)
        await page.fill("#p2-name", "Gary")
        # Default is 3 rounds — just start
        await page.click("#start-match-btn")
        for rnd in range(3):
            await page.wait_for_selector("#round-screen:not(.hidden)", timeout=10000)
            await wait_arena_sprite(page)
            # Both players answer
            await page.keyboard.press("q")
            await page.wait_for_timeout(200)
            await page.keyboard.press("i")
            await page.wait_for_selector("#round-result-screen:not(.hidden)", timeout=8000)
            await page.wait_for_timeout(400)
            next_btn = page.locator("#next-round-btn:not(.hidden)")
            if await next_btn.count() > 0:
                await next_btn.click()
            else:
                await page.wait_for_timeout(5500)
        await page.wait_for_selector("#match-end-screen:not(.hidden)", timeout=10000)
        await page.wait_for_timeout(700)
        await take(page, "20_battle_arena_match_end.png")
        await page.close()

        # ── 21 Arena Leaderboard ──────────────────────────────────────────────
        print("21 Arena Leaderboard")
        page = await new_page(browser)
        await page.goto(f"{BASE}/arena-leaderboard")
        await page.wait_for_selector("#solo-table:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(500)
        await take(page, "21_arena_leaderboard.png")
        await page.close()

        await browser.close()
        print("\nDone! All screenshots saved to screenshots/")

asyncio.run(main())
