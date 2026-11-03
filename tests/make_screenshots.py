"""Phone-sized screenshots of the app for review (docs/screenshots/).

Usage:  python -X utf8 -I tests/make_screenshots.py
"""
import os
import pathlib

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
URL = pathlib.Path(ROOT, "app", "index.html").as_uri()
OUT = os.path.join(ROOT, "docs", "screenshots")
GALAXY = dict(viewport={"width": 384, "height": 832}, device_scale_factor=2.8125, is_mobile=True, has_touch=True)


def shot(page, name):
    page.wait_for_timeout(400)
    path = os.path.join(OUT, name)
    page.screenshot(path=path)
    return path


def fill(page, k1, k2, al, target):
    page.fill("#k1", k1)
    page.fill("#k2", k2)
    page.fill("#al", al)
    page.select_option("#target", target)


def scroll_to_results(page):
    page.focus("#al")
    page.keyboard.press("Enter")


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    paths = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for scheme in ("light", "dark"):
            ctx = browser.new_context(color_scheme=scheme, **GALAXY)
            page = ctx.new_page()
            page.goto(URL)
            # two example lenses (illustrative names and constants)
            page.click("#nav-lenses")
            for name, a in [("Example lens A", "118.7"), ("Example lens B", "119.0")]:
                page.click("#addLens")
                page.fill("#edName", name)
                page.fill("#edA", a)
                page.click("#edSave")
            if scheme == "light":
                paths["lenses"] = shot(page, "5_lenses.png")
            page.click("#nav-calc")
            page.select_option("#lensSelect", label="Example lens A (A 118.7)")
            page.click("#eyeSeg button[data-eye='OD']")
            fill(page, "43.25", "43.75", "23.50", "-0.50")
            if scheme == "light":
                paths["input"] = shot(page, "1_input.png")
            scroll_to_results(page)
            if scheme == "light":
                paths["result"] = shot(page, "2_result.png")
                page.evaluate("document.getElementById('cmpTable').scrollIntoView({block: 'center'})")
                page.evaluate("document.querySelector('#resultCard details').open = true")
                page.evaluate("document.getElementById('cmpTable').scrollIntoView({block: 'end'})")
                paths["compare"] = shot(page, "3_compare.png")
                page.evaluate("window.scrollTo(0, 0)")
                fill(page, "48.00", "48.25", "28.00", "-0.50")
                scroll_to_results(page)
                paths["warning"] = shot(page, "4_warning.png")
                page.click("#nav-about")
                paths["about"] = shot(page, "6_about.png")
            else:
                paths["dark"] = shot(page, "7_dark.png")
            ctx.close()
        browser.close()

    # overview: three phone screens side by side
    sel = [("1. Input", paths["input"]), ("2. Result", paths["result"]), ("3. Lens list", paths["lenses"])]
    w, h, gap, top = 432, 936, 28, 70
    canvas = Image.new("RGB", (len(sel) * w + (len(sel) + 1) * gap, h + top + gap), (226, 232, 237))
    d = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 30)
    for i, (label, path) in enumerate(sel):
        img = Image.open(path).convert("RGB").resize((w, h), Image.LANCZOS)
        x = gap + i * (w + gap)
        canvas.paste(img, (x, top))
        d.rectangle([x - 1, top - 1, x + w, top + h], outline=(150, 160, 170), width=2)
        d.text((x, 22), label, font=font, fill=(20, 33, 44))
    canvas.save(os.path.join(OUT, "overview.png"))
    print("screenshots:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
