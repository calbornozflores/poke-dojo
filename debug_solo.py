"""Debug solo challenge flow."""
import asyncio
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
USERNAME = "Claudio"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()

        errors = []
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("requestfailed", lambda r: errors.append(f"[FAIL] {r.url} {r.failure}"))

        await page.add_init_script(f"localStorage.setItem('poke_username', '{USERNAME}');")
        await page.goto(f"{BASE}/battle-arena?mode=single")
        await page.wait_for_selector("#setup-single:not(.hidden)", timeout=8000)
        await page.wait_for_timeout(300)
        await page.keyboard.press("a")
        await page.wait_for_timeout(100)
        await page.keyboard.press("s")
        await page.wait_for_timeout(100)
        await page.keyboard.press("d")
        await page.wait_for_timeout(300)
        await page.fill("#solo-name", USERNAME)

        print("Clicking start...")
        await page.click("#start-match-btn")
        await page.wait_for_timeout(5000)

        # Print page state
        current_screens = await page.evaluate("""
          () => {
            const screens = ['setup-screen','round-screen','round-result-screen','single-gameover-screen','match-end-screen'];
            return screens.map(id => {
              const el = document.getElementById(id);
              return el ? `${id}: ${el.classList.contains('hidden') ? 'hidden' : 'VISIBLE'}` : `${id}: not found`;
            });
          }
        """)
        print("Screen states:")
        for s in current_screens:
            print(f"  {s}")

        setup_error = await page.text_content("#setup-error")
        print(f"Setup error text: '{setup_error}'")

        print("\nConsole errors:")
        for e in errors:
            print(f"  {e}")

        await browser.close()

asyncio.run(main())
