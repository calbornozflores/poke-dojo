"""
Screenshots 18-21 only (01-17 already done).
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
OUT = Path("screenshots")
USERNAME = "Claudio"

WAIT_ARENA_SPRITE = """
() => {
  const img = document.getElementById('arena-sprite');
  return img && img.complete && img.naturalWidth > 0 && !!img.src && img.src !== window.location.href;
}
"""

async def new_page(browser):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await ctx.new_page()
    await page.add_init_script(f"localStorage.setItem('poke_username', '{USERNAME}');")
    return page

async def take(page, name):
    await page.screenshot(path=str(OUT / name), full_page=False)
    print(f"  ✓ {name}")

async def wait_arena_sprite(page):
    await page.wait_for_function(WAIT_ARENA_SPRITE, timeout=15000)
    await page.wait_for_timeout(400)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        print("18 VS Round Result")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=vs")
        await page.wait_for_selector("#setup-vs:not(.hidden)", timeout=8000)
        await page.fill("#p2-name", "Gary")
        await page.click("#start-match-btn")
        await page.wait_for_selector("#round-screen:not(.hidden)", timeout=10000)
        await wait_arena_sprite(page)
        await page.keyboard.press("q")
        await page.wait_for_timeout(200)
        await page.keyboard.press("i")
        await page.wait_for_selector("#round-result-screen:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(600)
        await take(page, "18_battle_arena_vs_result.png")
        await page.close()

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

        print("20 Match End")
        page = await new_page(browser)
        await page.goto(f"{BASE}/battle-arena?mode=vs")
        await page.wait_for_selector("#setup-vs:not(.hidden)", timeout=8000)
        await page.fill("#p2-name", "Gary")
        await page.click("#start-match-btn")
        for _ in range(3):
            await page.wait_for_selector("#round-screen:not(.hidden)", timeout=10000)
            await wait_arena_sprite(page)
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

        print("21 Arena Leaderboard")
        page = await new_page(browser)
        await page.goto(f"{BASE}/arena-leaderboard")
        await page.wait_for_selector("#solo-table:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(500)
        await take(page, "21_arena_leaderboard.png")
        await page.close()

        await browser.close()
        print("Done!")

asyncio.run(main())
