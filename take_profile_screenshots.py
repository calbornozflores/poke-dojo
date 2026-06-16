"""Take profile and trainer journey screenshots after games are played."""
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

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        print("13 Profile")
        page = await new_page(browser)
        await page.goto(f"{BASE}/profile")
        await page.wait_for_load_state("networkidle")
        # Wait for profile content to render (bars, etc.)
        await page.wait_for_timeout(2000)
        await take(page, "13_profile.png")
        await page.close()

        print("14 Trainer Journey")
        page = await new_page(browser)
        await page.goto(f"{BASE}/journey")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)
        await take(page, "14_trainer_journey.png")
        await page.close()

        # Also retake leaderboard since Claudio now has real scores
        print("12 Leaderboard")
        page = await new_page(browser)
        await page.goto(f"{BASE}/leaderboard")
        await page.wait_for_selector("#global-table:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(500)
        await take(page, "12_leaderboard.png")
        await page.close()

        await browser.close()
        print("Done!")

asyncio.run(main())
