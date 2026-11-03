"""End-to-end tests of the app in headless Chrome with a Galaxy-sized screen.

Part A: app opened directly as a file (like a file copied to the phone).
Part B: app served over http with the service worker, then used with the network off.
Screenshots are written to docs/screenshots/.

Usage:  python -X utf8 -I tests/run_ui_tests.py
"""
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP_DIR = os.path.join(ROOT, "app")
FILE_URL = pathlib.Path(APP_DIR, "index.html").as_uri()
SHOTS = os.path.join(HERE, "output")
MINUS = "−"

GALAXY = dict(
    viewport={"width": 384, "height": 832}, device_scale_factor=2.8125, is_mobile=True, has_touch=True,
    user_agent="Mozilla/5.0 (Linux; Android 14; SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
)

results = []


def check(cond, msg):
    results.append((bool(cond), msg))
    print(("  PASS " if cond else "  FAIL ") + msg)


def fmt_num(x, d):
    s = f"{abs(x):.{d}f}"
    return s if float(s) == 0 else (MINUS if x < 0 else "") + s


def expected_power(page, K, AL, A, T, fid, pACD=None, SF=None):
    return page.evaluate(
        "([K, AL, A, T, fid, pACD, SF]) => IOLEngine.computeAll({K, AL, A, target: T, pACD, SF}).byId[fid].forTarget",
        [K, AL, A, T, fid, pACD, SF])


def enter(page, k1, k2, al, target=None):
    page.fill("#k1", k1)
    page.fill("#k2", k2)
    page.fill("#al", al)
    page.locator("#al").blur()
    if target is not None:
        page.select_option("#target", target)


def codes(page):
    return page.eval_on_selector_all("#results .msg[data-code]", "els => els.map(e => e.dataset.code)")


def part_a(p):
    print("\n== Part A: opened as a file")
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(**GALAXY)
    page = ctx.new_page()
    errors, requests = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))
    page.goto(FILE_URL)

    check(page.is_hidden("#selftestBanner"), "self-test banner hidden (self-test passed)")
    check("Enter K1, K2, axial length" in page.inner_text("#results"), "placeholder shown before input")

    # --- main calculation, SRK/T, sample lens A 118.0
    enter(page, "43.25", "43.75", "23.5", "-0.50")
    exp = expected_power(page, 43.5, 23.5, 118.0, -0.5, "srkt")
    check(page.inner_text("#resPower") == fmt_num(exp, 2), f"SRK/T power shown {page.inner_text('#resPower')} == engine {exp:.4f}")
    check("Mean K 43.50 D" in page.inner_text("#kline"), "mean K line")
    rows = page.eval_on_selector_all("#rxTable tbody tr", "trs => trs.map(t => [t.className, t.cells[0].innerText, t.cells[1].innerText])")
    check(len(rows) == 13, f"lens table has 13 rows ({len(rows)})")
    check(sum(1 for r in rows if r[0] == "closest") == 1, "exactly one highlighted row")
    vals = [float(r[2].replace(MINUS, "-").replace("+", "")) for r in rows]
    check(all(a < b for a, b in zip(vals, vals[1:])), "predicted refraction rises as IOL power falls")

    # --- every formula via the segmented buttons
    for fid, label in [("hofferq", "Hoffer Q"), ("holladay1", "Holladay 1"), ("srk2", "SRK II"), ("srkt", "SRK/T")]:
        page.click(f"#formulaSeg button[data-formula='{fid}']")
        exp = expected_power(page, 43.5, 23.5, 118.0, -0.5, fid)
        check(page.inner_text("#resPower") == fmt_num(exp, 2) and label in page.inner_text("#resultCard"),
              f"{label}: shown {page.inner_text('#resPower')} == engine {exp:.4f}")
        sel = page.get_attribute("#cmpTable tr.sel", "data-formula")
        check(sel == fid, f"{label}: compare table highlights selected formula")
    page.click("#cmpTable tr[data-formula='holladay1']")
    check(page.get_attribute("#formulaSeg button[data-formula='holladay1']", "aria-pressed") == "true", "tapping a compare row selects that formula")
    page.click("#formulaSeg button[data-formula='srkt']")

    # --- 'done' on the AL keyboard scrolls down to the result
    page.evaluate("window.scrollTo(0, 0)")
    page.focus("#al")
    page.keyboard.press("Enter")
    page.wait_for_timeout(700)
    check(page.evaluate("window.scrollY") > 300, "Enter on axial length scrolls to the result")
    check(page.inner_text("#resNearest") == "21.0 D", f"nearest 0.5 D lens shown ({page.inner_text('#resNearest')})")
    page.evaluate("window.scrollTo(0, 0)")

    # --- eye badge
    page.click("#eyeSeg button[data-eye='OD']")
    check(page.inner_text("#resultCard .eye-badge") == "OD", "OD badge shown in result")
    page.screenshot(path=os.path.join(SHOTS, "01_calculator.png"), full_page=True)
    page.click("#eyeSeg button[data-eye='OD']")
    check(page.inner_text("#resultCard .eye-badge") == "Eye?", "tapping OD again clears the eye")

    # --- K unit mm
    before = page.inner_text("#resPower")
    page.click("#kUnitSeg button[data-unit='mm']")
    check(page.input_value("#k1") == "7.803" and page.input_value("#k2") == "7.714", f"K converted to mm ({page.input_value('#k1')}, {page.input_value('#k2')})")
    after = float(page.inner_text("#resPower").replace(MINUS, "-"))
    check(abs(after - float(before.replace(MINUS, "-"))) <= 0.011, f"result unchanged after unit switch ({before} vs {after})")
    page.click("#kUnitSeg button[data-unit='D']")
    check(page.input_value("#k1") == "43.25", "K converted back to D")

    # --- decimal comma and validation
    page.fill("#k1", "43,25")
    check(page.inner_text("#resPower") == before, "decimal comma accepted")
    page.fill("#al", "2")
    page.locator("#al").blur()
    check("Allowed 15 to 40" in page.inner_text("#alecho") and "invalid" in (page.get_attribute("#al", "class") or ""),
          "out-of-range AL shows an error")
    check("Enter axial length" in page.inner_text("#results"), "no result while AL is invalid")

    # --- warnings
    enter(page, "48", "48", "28")
    c = codes(page)
    check("srkt-limit" in c, f"steep + long eye: SRK/T geometric-limit alert ({c})")
    page.screenshot(path=os.path.join(SHOTS, "02_warning_steep_long_eye.png"), full_page=True)
    enter(page, "46.5", "46.5", "26.5")
    check("srkt-near" in codes(page), "SRK/T near-limit caution")
    enter(page, "43.5", "43.5", "34")
    c = codes(page)
    check({"hq-clamp", "al-long", "hint-long"} <= set(c), f"AL 34: Hoffer Q AL limit, long-eye caution and hint ({c})")
    enter(page, "42", "46", "23.5")
    check("k-astig" in codes(page), "astigmatism > 3 D caution")
    enter(page, "47", "47", "18")
    c = codes(page)
    check({"spread", "al-short", "hint-short", "power-range"} <= set(c), f"AL 18: spread, short-eye, power-range ({c})")
    enter(page, "43.5", "43.5", "23.5")
    check(codes(page) == [], "normal eye: no warnings")

    # --- new patient
    page.click("#newPatient")
    check(page.input_value("#k1") == "" and page.input_value("#al") == "" and "Enter K1" in page.inner_text("#results"),
          "New patient clears the inputs and result")

    # --- lens list: add, use, edit, validate, persist, delete
    page.click("#nav-lenses")
    page.click("#addLens")
    page.fill("#edName", "Test IOL")
    page.fill("#edA", "118.7")
    check("5.37" in page.inner_text("#edPecho"), "editor shows derived pACD (5.37 for A 118.7) for blank field")
    page.fill("#edP", "5.20")
    page.fill("#edS", "1.50")
    page.click("#edSave")
    check("Test IOL" in page.inner_text("#lensList") and page.is_hidden("#lensEditor"), "lens added")
    page.screenshot(path=os.path.join(SHOTS, "04_lenses.png"), full_page=True)
    page.click("#nav-calc")
    check("Test IOL (A 118.7)" in page.inner_text("#lensSelect"), "new lens appears and is selected")
    page.click("#formulaSeg button[data-formula='hofferq']")
    enter(page, "44", "44.5", "22.8", "0.00")
    exp = expected_power(page, 44.25, 22.8, 118.7, 0.0, "hofferq", pACD=5.2, SF=1.5)
    check(page.inner_text("#resPower") == fmt_num(exp, 2), f"Hoffer Q uses entered pACD 5.20 ({page.inner_text('#resPower')} vs {exp:.4f})")
    check("pACD 5.20" in page.inner_text("#resultCard") and "(from A)" not in page.inner_text("#resultCard .res-lens"), "entered pACD shown without 'from A'")
    page.click("#formulaSeg button[data-formula='holladay1']")
    exp = expected_power(page, 44.25, 22.8, 118.7, 0.0, "holladay1", pACD=5.2, SF=1.5)
    check(page.inner_text("#resPower") == fmt_num(exp, 2), "Holladay 1 uses entered SF 1.50")

    page.click("#nav-lenses")
    page.click("#lensList button[data-edit]:right-of(:text('Test IOL'))")
    page.fill("#edA", "130")
    page.click("#edSave")
    check(page.is_visible("#edError") and "between 110 and 125" in page.inner_text("#edError"), "invalid A-constant rejected")
    page.screenshot(path=os.path.join(SHOTS, "05_lens_editor.png"), full_page=True)
    page.fill("#edA", "119.2")
    page.click("#edSave")
    check("A 119.2" in page.inner_text("#lensList"), "lens edited")
    page.select_option("#defTarget", "-0.50")

    stored = json.loads(page.evaluate("localStorage.getItem('iolcalc.settings.v1')"))
    check(set(stored) == {"v", "lenses", "selectedLensId", "formula", "kUnit", "defaultTarget"},
          f"only settings are stored, no patient data ({sorted(stored)})")
    check("44.25" not in json.dumps(stored) and "22.8" not in json.dumps(stored), "K and AL values are not in storage")

    page.reload()
    page.click("#nav-lenses")
    check("Test IOL" in page.inner_text("#lensList"), "lens list kept after closing and reopening")
    page.click("#nav-calc")
    check(page.input_value("#k1") == "" and page.input_value("#target") == "-0.50", "after reopening: patient fields empty, default target applied")
    check(page.get_attribute("#formulaSeg button[data-formula='holladay1']", "aria-pressed") == "true", "last formula remembered")

    page.click("#nav-lenses")
    page.once("dialog", lambda d: d.accept())
    page.click("#lensList button[data-edit]:right-of(:text('Test IOL'))")
    page.click("#edDelete")
    check("Test IOL" not in page.inner_text("#lensList"), "lens deleted after confirmation")

    page.click("#nav-about")
    status = page.inner_text("#statusList")
    check("Self-test passed (8 reference cases)" in status, "About: self-test passed")
    page.screenshot(path=os.path.join(SHOTS, "06_about.png"), full_page=True)

    external = [u for u in requests if not u.startswith("file:")]
    check(not external, f"no network requests outside the app files ({external[:3]})")
    check(not errors, f"no console errors ({errors[:3]})")
    ctx.close()

    # --- dark mode screenshot
    ctx = browser.new_context(color_scheme="dark", **GALAXY)
    page = ctx.new_page()
    page.goto(FILE_URL)
    page.click("#eyeSeg button[data-eye='OS']")
    enter(page, "44.00", "44.50", "24.10", "-0.25")
    page.screenshot(path=os.path.join(SHOTS, "03_dark_mode.png"), full_page=True)
    check(page.inner_text("#resultCard .eye-badge") == "OS", "dark mode renders the result")
    ctx.close()
    browser.close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def part_b(p):
    print("\n== Part B: installed web app, then offline")
    port = free_port()
    server = subprocess.Popen([sys.executable, "-I", "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", APP_DIR],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{port}/index.html"
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(**GALAXY)
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(url)
        page.evaluate("navigator.serviceWorker.ready.then(() => true)")
        page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=10000)
        check(True, "service worker installed and controlling the page")
        man = page.evaluate("fetch('manifest.webmanifest').then(r => r.json())")
        check(man.get("display") == "standalone" and len(man.get("icons", [])) == 3, "manifest is valid for installation")
        icons_ok = page.evaluate("Promise.all(['icon-192.png','icon-512.png','icon-maskable-512.png'].map(u => fetch(u).then(r => r.ok)))")
        check(all(icons_ok), "icons load")
        page.click("#nav-lenses")
        page.click("#addLens")
        page.fill("#edName", "Mission IOL")
        page.fill("#edA", "118.4")
        page.click("#edSave")

        server.terminate()
        server.wait(5)
        ctx.set_offline(True)
        page.reload()
        check(page.title() == "IOL Calculator", "app opens with the server stopped and the network off")
        enter(page, "43.5", "44.0", "23.2", "0.00")
        exp = expected_power(page, 43.75, 23.2, 118.4, 0.0, "srkt")
        check(page.inner_text("#resPower") == fmt_num(exp, 2), "offline calculation works with the saved lens")
        page.click("#nav-about")
        check("Installed copy: works without internet" in page.inner_text("#statusList"), "About shows installed offline copy")
        check(not errors, f"no console errors ({errors[:3]})")
        browser.close()
    finally:
        if server.poll() is None:
            server.terminate()


if __name__ == "__main__":
    os.makedirs(SHOTS, exist_ok=True)
    with sync_playwright() as p:
        part_a(p)
        part_b(p)
    failed = [m for ok, m in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)}/{len(results)} passed")
    for m in failed:
        print("  FAILED:", m)
    sys.exit(1 if failed else 0)
