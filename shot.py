import asyncio, sys
from playwright.async_api import async_playwright

SCRIPT = sys.argv[1] if len(sys.argv) > 1 else "guide.py"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/pw_shot.png"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader-webgl"])
        pg = await b.new_page(viewport={"width": 1400, "height": 850})
        logs = []
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
        await pg.goto("http://127.0.0.1:8770/", wait_until="load", timeout=15000)
        await pg.wait_for_timeout(3000)
        try:
            await pg.get_by_text(SCRIPT, exact=True).first.click(timeout=4000)
        except Exception as e:
            logs.append(f"click fail: {e}")
        await pg.wait_for_timeout(3500)
        await pg.screenshot(path=OUT)
        n_items = await pg.eval_on_selector_all(".item", "els=>els.length")
        n_params = await pg.eval_on_selector_all(".prow", "els=>els.length")
        hud = await pg.text_content("#hud")
        canvas = await pg.eval_on_selector("#canvas", "c=>[c.clientWidth,c.clientHeight]")
        print("items:", n_items, "param rows:", n_params, "canvas:", canvas)
        print("hud:", hud)
        print("--- console (last 15) ---")
        for l in logs[-15:]:
            print(l)
        await b.close()

asyncio.run(main())
