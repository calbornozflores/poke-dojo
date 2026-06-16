"""Verify and retake screenshots for the 4 UI changes."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
OUT = Path("screenshots")
USERNAME = "Claudio"

async def new_page(browser):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await ctx.new_page()
    await page.add_init_script(f"localStorage.setItem('poke_username', '{USERNAME}');")
    return page

async def take(page, name):
    await page.screenshot(path=str(OUT / name), full_page=False)
    print(f"  ✓ {name}")

WAIT_ARENA_SPRITE = """
() => {
  const img = document.getElementById('arena-sprite');
  return img && img.complete && img.naturalWidth > 0 && !!img.src && img.src !== window.location.href;
}
"""

async def click_wrong_option(page):
    """Click the wrong option by reading roundData.correct_position from JS context."""
    await page.evaluate("""
      () => {
        // Find the wrong option: use pos 1 unless correct is 1, then use 2
        const correct = window.roundData ? window.roundData.correct_position : 1;
        const wrong = correct === 1 ? 2 : 1;
        const btn = document.querySelector(`.arena-option-btn[data-pos="${wrong}"]`);
        if (btn) btn.click();
      }
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # ── Play page — VS Mode (Metapod icons) + Solo (Mewtwo icon) ─────────
        print("02 Play intro (VS/Solo icons)")
        page = await new_page(browser)
        await page.goto(f"{BASE}/play")
        await page.wait_for_selector("#btn-vs", timeout=5000)
        # Wait for pixel sprites to load
        await page.wait_for_function("""
          () => {
            const imgs = document.querySelectorAll('.battle-btn-sprite');
            return imgs.length > 0 && Array.from(imgs).every(i => i.complete && i.naturalWidth > 0);
          }
        """, timeout=10000)
        await page.wait_for_timeout(300)
        await take(page, "02_play_intro.png")
        await page.close()

        # ── Profile — AI bars only ────────────────────────────────────────────
        print("13 Profile (AI bars only)")
        page = await new_page(browser)
        await page.goto(f"{BASE}/profile")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)
        await take(page, "13_profile.png")
        await page.close()

        # ── Solo gameover — Gastly (lose < 10 rounds) ─────────────────────────
        print("Solo gameover — Gastly")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=single")
        await page.wait_for_selector("#setup-single:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(300)
        # Assign keys A/S/D
        await page.keyboard.press("a")
        await page.wait_for_timeout(100)
        await page.keyboard.press("s")
        await page.wait_for_timeout(100)
        await page.keyboard.press("d")
        await page.wait_for_timeout(300)
        # Verify keys assigned before clicking start
        k0 = await page.text_content("#key-slot-0")
        k1 = await page.text_content("#key-slot-1")
        k2 = await page.text_content("#key-slot-2")
        print(f"    Keys: {k0}/{k1}/{k2}")
        # Click start (solo-name is auto-filled from localStorage)
        await page.evaluate("document.getElementById('start-match-btn').click()")
        await page.wait_for_timeout(6000)  # wait for API + round load
        # Lose all 3 lives: each wrong answer → flash → round-result-screen → Next → repeat
        # Last life goes directly to gameover (no round-result-screen)
        for life in range(3):
            await page.wait_for_selector("#round-screen:not(.hidden)", timeout=20000)
            await page.wait_for_function(WAIT_ARENA_SPRITE, timeout=15000)
            await page.wait_for_timeout(400)
            await click_wrong_option(page)
            await page.wait_for_timeout(2500)  # flash duration (1.3s) + server response
            if life < 2:
                # Still lives left: round-result-screen appears, click Next
                await page.wait_for_selector("#round-result-screen:not(.hidden)", timeout=8000)
                await page.wait_for_timeout(300)
                await page.evaluate("document.getElementById('next-round-btn').click()")
                await page.wait_for_timeout(1500)
        # After 3rd wrong: gameover screen appears directly
        await page.wait_for_selector("#single-gameover-screen:not(.hidden)", timeout=15000)
        # Wait for Gastly image to load
        await page.wait_for_function("""
          () => {
            const img = document.querySelector('#analytics-emoji img');
            return img && img.complete && img.naturalWidth > 0;
          }
        """, timeout=10000)
        await page.wait_for_timeout(500)
        await take(page, "20b_solo_gameover.png")
        await page.close()

        await browser.close()
        print("Done!")

asyncio.run(main())
