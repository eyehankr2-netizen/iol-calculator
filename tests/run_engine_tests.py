"""Run the app's JavaScript engine in headless Chrome and compare it with
(1) the user's spreadsheet formulas (tests/excel_cases.json, from excel_reference.py)
(2) the independent Python implementation (tests/reference_cases.json, from reference_impl.py)

Usage:  python -X utf8 -I tests/run_engine_tests.py
Writes tests/engine_report.json and prints a summary. Exit code 1 on any failure.
"""
import json
import math
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = pathlib.Path(ROOT, "app", "index.html").as_uri()
EXCEL_OPTS = {"lcorThreshold": 24.4, "haigisClamp": False, "hofferAlClamp": False}
TOL = 1e-9

JS_RUN = """
([cases, opts]) => cases.map(c => {
  const r = IOLEngine.computeAll({K: c.K, AL: c.AL, A: c.A, target: c.T || 0}, opts);
  const out = {};
  for (const id of IOLEngine.FORMULA_IDS) {
    const f = r.byId[id];
    out[id] = f.ok ? {ok: true, emme: f.emme, forTarget: f.forTarget,
                      rx: c.P.map(p => f.refraction(p)), d: f.details, flags: f.flags,
                      roundtrip: [-3, -1, -0.5, 0, 0.5, 1, 2].map(t => f.refraction(f.power(t)) - t)}
                   : {ok: false};
  }
  return out;
})
"""


class Stat:
    def __init__(self, name):
        self.name, self.n, self.max, self.fail, self.where = name, 0, 0.0, 0, None

    def add(self, got, exp, ctx, tol=TOL):
        self.n += 1
        if got is None or exp is None or not math.isfinite(got) or not math.isfinite(exp):
            self.fail += 1
            self.where = self.where or (ctx, got, exp)
            return
        d = abs(got - exp)
        if d > self.max:
            self.max = d
        if d > tol:
            self.fail += 1
            self.where = self.where or (ctx, got, exp)

    def row(self):
        return {"check": self.name, "n": self.n, "max_abs_diff": self.max, "failures": self.fail,
                "first_failure": self.where}


def main():
    excel = json.load(open(os.path.join(HERE, "excel_cases.json"), encoding="utf-8"))
    ref = json.load(open(os.path.join(HERE, "reference_cases.json"), encoding="utf-8"))
    report = {"app": APP}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(APP)
        st = page.evaluate("IOLEngine.selfTest()")
        report["selftest"] = st
        excel_js = page.evaluate(JS_RUN, [[{"K": c["K"], "AL": c["AL"], "A": c["A"], "P": c["P"]} for c in excel], EXCEL_OPTS])
        ref_app_js = page.evaluate(JS_RUN, [[{"K": c["K"], "AL": c["AL"], "A": c["A"], "T": c["T"], "P": c["P"]} for c in ref], None])
        ref_xl_js = page.evaluate(JS_RUN, [[{"K": c["K"], "AL": c["AL"], "A": c["A"], "T": c["T"], "P": c["P"]} for c in ref], EXCEL_OPTS])
        browser.close()

    # ---------- 1. engine (spreadsheet mode) vs the user's spreadsheet formulas
    s = {k: Stat("excel " + k) for k in ["srkt_LCOR", "srkt_ELP", "srkt_emme", "srkt_rx", "srkt_not_computable",
                                         "hq_ACD", "hq_emme", "hq_rx", "hol_ACD", "hol_ELP", "hol_emme", "hol_rx"]}
    for c, j in zip(excel, excel_js):
        o, ctx = c["out"], (c["K"], c["AL"], c["A"])
        if o["srkt_emme"] is None:
            s["srkt_not_computable"].add(0.0 if not j["srkt"]["ok"] else 1.0, 0.0, ctx)
        else:
            js = j["srkt"]
            s["srkt_LCOR"].add(js["d"]["LCOR"], o["srkt_LCOR"], ctx)
            s["srkt_ELP"].add(js["d"]["ELP"], o["srkt_ELP"], ctx)
            s["srkt_emme"].add(js["emme"], o["srkt_emme"], ctx)
            for g, e in zip(js["rx"], o["srkt_rx"]):
                s["srkt_rx"].add(g, e, ctx)
        jq, jh = j["hofferq"], j["holladay1"]
        s["hq_ACD"].add(jq["d"]["ACD"], o["hq_ACD"], ctx)
        s["hq_emme"].add(jq["emme"], o["hq_emme"], ctx)
        for g, e in zip(jq["rx"], o["hq_rx"]):
            s["hq_rx"].add(g, e, ctx)
        s["hol_ACD"].add(jh["d"]["ACD"], o["hol_ACD"], ctx)
        s["hol_ELP"].add(jh["d"]["ELP"], o["hol_ELP"], ctx)
        s["hol_emme"].add(jh["emme"], o["hol_emme"], ctx)
        for g, e in zip(jh["rx"], o["hol_rx"]):
            s["hol_rx"].add(g, e, ctx)
    report["vs_spreadsheet"] = [x.row() for x in s.values()]

    # ---------- 2. engine vs independent Python implementation (app mode and spreadsheet mode)
    def compare(label, js_list, mode):
        st = {}
        for c, j in zip(ref, js_list):
            ctx = (c["K"], c["AL"], c["A"], c["T"])
            for fid in ["srkt", "hofferq", "holladay1", "srk2"]:
                e, g = c[mode][fid], j[fid]
                key = f"{label} {fid}"
                if not e["ok"]:
                    st.setdefault(key + " not computable", Stat(key + " not computable")).add(0.0 if not g["ok"] else 1.0, 0.0, ctx)
                    continue
                for name, gv, ev in [("emme", g.get("emme"), e["emme"]), ("forTarget", g.get("forTarget"), e["forTarget"])]:
                    st.setdefault(f"{key} {name}", Stat(f"{key} {name}")).add(gv, ev, ctx, 1e-7)
                for gv, ev in zip(g.get("rx", [None] * 3), e["rx"]):
                    st.setdefault(f"{key} rx", Stat(f"{key} rx")).add(gv, ev, ctx)
                rt = Stat("")
                for v in g.get("roundtrip", []):
                    st.setdefault(f"{key} roundtrip", Stat(f"{key} roundtrip")).add(v, 0.0, ctx, 1e-9)
        return [x.row() for x in st.values()]

    report["vs_python_app_mode"] = compare("app", ref_app_js, "app")
    report["vs_python_spreadsheet_mode"] = compare("sheet", ref_xl_js, "excel")

    # ---------- 3. how the app differs from the spreadsheet (informational)
    diffs = {"srkt": [], "hofferq": []}
    for c in ref:
        for fid in diffs:
            a, x = c["app"][fid], c["excel"][fid]
            if a["ok"] and x["ok"]:
                d = abs(a["emme"] - x["emme"])
                if d > 1e-9:
                    diffs[fid].append({"K": c["K"], "AL": c["AL"], "A": c["A"], "diff": d})
            elif a["ok"] and not x["ok"]:
                diffs[fid].append({"K": c["K"], "AL": c["AL"], "A": c["A"], "diff": None})
    report["app_vs_spreadsheet_differences"] = {
        fid: {"cases_differing": len(v),
              "AL_values": sorted({d["AL"] for d in v}),
              "max_diff_where_both_computable": max([d["diff"] for d in v if d["diff"] is not None], default=0.0),
              "spreadsheet_not_computable": sum(1 for d in v if d["diff"] is None)}
        for fid, v in diffs.items()}
    iol = [abs(c["app"]["srkt"]["emme"] - c["iolsolver"]["srkt"]["emme"]) for c in ref]
    report["srkt_constant_variant_max_diff"] = max(iol)
    report["console_errors"] = errors

    with open(os.path.join(HERE, "engine_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)

    # ---------- summary
    bad = 0
    print("self-test in page:", "PASS" if st["pass"] else "FAIL", st["n"], "cases", st["failures"][:3])
    bad += 0 if st["pass"] else 1
    for section in ["vs_spreadsheet", "vs_python_app_mode", "vs_python_spreadsheet_mode"]:
        rows = report[section]
        nf = sum(r["failures"] for r in rows)
        print(f"\n== {section}: {sum(r['n'] for r in rows)} comparisons, failures {nf}")
        for r in rows:
            flag = "OK " if r["failures"] == 0 else "FAIL"
            print(f"  {flag} {r['check']:<38} n={r['n']:<5} max|diff|={r['max_abs_diff']:.2e}" + (f"  first={r['first_failure']}" if r["failures"] else ""))
        bad += nf
    print("\n== app vs spreadsheet (expected differences):")
    for fid, v in report["app_vs_spreadsheet_differences"].items():
        print(f"  {fid}: {v}")
    print(f"  SRK/T with the alternative constants (-5.40948 / 1.715): max diff {report['srkt_constant_variant_max_diff']:.4f} D")
    print("console errors:", errors or "none")
    bad += len(errors)
    print("\nRESULT:", "ALL PASS" if bad == 0 else f"{bad} FAILURES")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
