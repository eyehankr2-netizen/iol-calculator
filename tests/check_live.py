"""Check the published app (GitHub Pages) the way a phone would use it.

Usage:  python -X utf8 -I tests/check_live.py [base_url]
Default base_url: https://eyehankr2-netizen.github.io/iol-calculator/
"""
import hashlib
import os
import sys
import tempfile
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://eyehankr2-netizen.github.io/iol-calculator/").rstrip("/") + "/"
GALAXY = dict(viewport={"width": 384, "height": 832}, device_scale_factor=2.8125, is_mobile=True, has_touch=True,
              user_agent="Mozilla/5.0 (Linux; Android 14; SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")
results = []


def check(cond, msg):
    results.append((bool(cond), msg))
    print(("  PASS " if cond else "  FAIL ") + msg)


def main():
    # deployed files are byte-identical to the tested local files
    for f in ["index.html", "sw.js", "manifest.webmanifest", "icon-192.png", "icon-512.png", "icon-maskable-512.png"]:
        live = urllib.request.urlopen(BASE + "app/" + f, timeout=20).read()
        local = open(os.path.join(ROOT, "app", f), "rb").read()
        check(hashlib.sha256(live).digest() == hashlib.sha256(local).digest(), f"published app/{f} matches the tested file")

    with sync_playwright() as p:
        # a normal (non-incognito) profile, like a phone browser, so Chrome can judge installability
        profile = tempfile.mkdtemp(prefix="iolcalc-live-")
        ctx = p.chromium.launch_persistent_context(profile, channel="chrome", headless=True, **GALAXY)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        errors, missing = [], []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: missing.append(f"{r.status} {r.url}") if r.status >= 400 else None)

        page.goto(BASE)
        page.wait_for_url("**/app/**", timeout=15000)
        check(page.title() == "IOL Calculator", f"short address opens the app ({page.url})")
        check(page.is_hidden("#selftestBanner"), "self-test passed on the published copy")

        page.evaluate("navigator.serviceWorker.ready.then(() => true)")
        page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
        check(True, "offline copy (service worker) installed")

        cdp = ctx.new_cdp_session(page)
        inst = cdp.send("Page.getInstallabilityErrors").get("installabilityErrors", [])
        check(not inst, f"Chrome reports the app as installable ({inst})")

        page.click("#nav-lenses")
        page.click("#addLens")
        page.fill("#edName", "Live check lens")
        page.fill("#edA", "118.4")
        page.click("#edSave")

        ctx.set_offline(True)
        page.reload()
        check(page.title() == "IOL Calculator", "opens with the network off")
        page.fill("#k1", "43.5")
        page.fill("#k2", "44.0")
        page.fill("#al", "23.2")
        page.select_option("#target", "0.00")
        exp = page.evaluate("IOLEngine.computeAll({K: 43.75, AL: 23.2, A: 118.4, target: 0}).byId.srkt.forTarget")
        check(page.inner_text("#resPower") == f"{exp:.2f}", f"offline calculation with the saved lens ({page.inner_text('#resPower')} D)")
        page.click("#nav-about")
        check("Installed copy: works without internet" in page.inner_text("#statusList"), "About shows the installed offline copy")
        check(not errors, f"no console errors ({errors[:3]} {missing[:3]})")
        ctx.close()

    failed = [m for ok, m in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
