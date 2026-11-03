"""Independent reference implementation used to verify the app's JavaScript engine.

This file is written separately from app/index.html.

Sources
- SRK/T: refraction formula of the user's spreadsheet (column D) and the IOLSolver
  implementation (news.iolsolver.com). LCOR threshold 24.2 mm (1990 erratum).
  Negative square-root term set to 0 (Haigis 1993 letter and authors' reply).
- Hoffer Q: spreadsheet column F and IOLSolver code. AL limited to 18.5-31 mm for the
  ACD prediction (Hoffer 2007 erratum).
- Holladay 1: spreadsheet column H and IOLSolver code.
- SRK II: Tomey UD-800 manual, Sanders 1988.

The IOL power for a target refraction is found numerically (bisection on the
refraction function). The app uses closed-form power formulas, so this checks them
independently.

Usage:  python -X utf8 -I tests/reference_impl.py
  writes tests/reference_cases.json and injects the self-test cases into app/index.html
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


# ---------------------------------------------------------------- formulas
def srkt_model(K, AL, A, lcor_cut=24.2, clamp=True, cw0=-5.41, lc1=1.716):
    r = 337.5 / K
    LCOR = AL if AL <= lcor_cut else -3.446 + lc1 * AL - 0.0237 * AL ** 2
    Cw = cw0 + 0.58412 * LCOR + 0.098 * K
    x = r ** 2 - Cw ** 2 / 4.0
    limit = x < 0
    if limit:
        if not clamp:
            return None
        x = 0.0
    H = r - math.sqrt(x)
    ACDest = H + (0.62467 * A - 68.747) - 3.336
    LOPT = AL + 0.65696 - 0.02029 * AL
    na, ncml, V = 1.336, 0.333, 12.0

    def rx(P):
        num = 1000 * na * (na * r - ncml * LOPT) - P * (LOPT - ACDest) * (na * r - ncml * ACDest)
        den = (na * (V * (na * r - ncml * LOPT) + LOPT * r)
               - 0.001 * P * (LOPT - ACDest) * (V * (na * r - ncml * ACDest) + ACDest * r))
        return num / den

    return {"rx": rx, "LCOR": LCOR, "ELP": ACDest, "H": H, "limit": limit, "ratio": Cw / (2 * r)}


def hofferq_model(K, AL, pACD, al_clamp=True):
    if AL <= 23.0:
        M, G = 1.0, 28.0
    else:
        M, G = -1.0, 23.5
    La = AL
    if al_clamp:
        if AL > 31.0:
            La = 31.0
        elif AL < 18.5:
            La = 18.5
    p2 = 0.3 * (La - 23.5)
    p3 = math.tan(K * math.pi / 180.0) ** 2
    p4 = 0.1 * M * (23.5 - La) ** 2
    p5 = math.tan(0.1 * (G - La) ** 2 * math.pi / 180.0)
    ACD = pACD + p2 + p3 + p4 * p5 - 0.99166

    def rx(P):
        R = 1.336 / (1.336 / (1336.0 / (AL - ACD - 0.05) - P) + (ACD + 0.05) / 1000.0) - K
        return R / (1.0 + 0.012 * R)

    return {"rx": rx, "ACD": ACD, "clamped": La != AL}


def holladay1_model(K, AL, SF):
    R = 337.5 / K
    Rag = 7.0 if R < 7.0 else R
    AG = 12.5 * AL / 23.45
    if AG > 13.5:
        AG = 13.5
    ACD = 0.56 + Rag - math.sqrt(Rag ** 2 - AG ** 2 / 4.0)
    nc, na, RT, V = 4.0 / 3.0, 1.336, 0.2, 12.0
    ALm = AL + RT

    def rx(P):
        num = 1000 * na * (na * R - (nc - 1) * ALm) - P * (ALm - ACD - SF) * (na * R - (nc - 1) * (ACD + SF))
        den = (na * (V * (na * R - (nc - 1) * ALm) + ALm * R)
               - 0.001 * P * (ALm - ACD - SF) * (V * (na * R - (nc - 1) * (ACD + SF)) + (ACD + SF) * R))
        return num / den

    return {"rx": rx, "ACD": ACD, "ELP": ACD + SF}


def srk2_model(K, AL, A):
    if AL < 20.0:
        A1 = A + 3
    elif AL < 21.0:
        A1 = A + 2
    elif AL < 22.0:
        A1 = A + 1
    elif AL < 24.5:
        A1 = A
    else:
        A1 = A - 0.5
    Pe = A1 - 2.5 * AL - 0.9 * K
    CR = 1.25 if Pe > 14 else 1.0
    return {"rx": lambda P: (Pe - P) / CR, "A1": A1, "CR": CR}


def invert(rx, target, lo=-40.0, hi=80.0, step=0.5):
    """IOL power P with rx(P) == target. rx decreases as P increases.
    Scans upward for the first sign change without a pole jump, then bisects."""
    P = lo
    while P < hi:
        a, b = rx(P) - target, rx(P + step) - target
        if a > 0 >= b and abs(a - b) < 20:
            lo2, hi2 = P, P + step
            for _ in range(200):
                mid = 0.5 * (lo2 + hi2)
                if rx(mid) - target > 0:
                    lo2 = mid
                else:
                    hi2 = mid
            return 0.5 * (lo2 + hi2)
        P += step
    raise ValueError("target not bracketed")


def pacd_from_a(A):
    return 0.58357 * A - 63.896


def sf_from_a(A):
    return 0.5663 * A - 65.6


def models(K, AL, A, mode="app"):
    """mode 'app': 24.2 + clamps.  mode 'excel': spreadsheet behaviour (24.4, no clamps)."""
    if mode == "app":
        s = srkt_model(K, AL, A)
        h = hofferq_model(K, AL, pacd_from_a(A))
    elif mode == "excel":
        s = srkt_model(K, AL, A, lcor_cut=24.4, clamp=False)
        h = hofferq_model(K, AL, pacd_from_a(A), al_clamp=False)
    elif mode == "iolsolver":
        s = srkt_model(K, AL, A, cw0=-5.40948, lc1=1.715)
        h = hofferq_model(K, AL, pacd_from_a(A))
    else:
        raise ValueError(mode)
    return {"srkt": s, "hofferq": h, "holladay1": holladay1_model(K, AL, sf_from_a(A)), "srk2": srk2_model(K, AL, A)}


def expected(K, AL, A, T, Ps, mode="app"):
    out = {}
    for fid, m in models(K, AL, A, mode).items():
        if m is None:
            out[fid] = {"ok": False}
            continue
        e = {"ok": True, "emme": invert(m["rx"], 0.0), "forTarget": invert(m["rx"], T), "rx": [m["rx"](p) for p in Ps]}
        for k, v in m.items():
            if k != "rx":
                e[k] = v
        out[fid] = e
    return out


# ---------------------------------------------------------------- case sets
AL_GRID = [17.5, 19.0, 20.0, 21.0, 22.0, 23.0, 23.5, 24.0, 24.2, 24.3, 24.4, 24.5, 25.0, 26.0, 27.0, 28.0, 30.0, 32.0, 34.0]
K_GRID = [38.0, 41.0, 43.5, 45.0, 47.0, 49.0]
A_GRID = [118.0, 118.9]
T_GRID = [0.0, -0.5, -2.0, 1.0]

SELFTEST_INPUTS = [  # K, AL, A, target, P
    (43.5, 23.5, 118.7, -0.5, 21.0),
    (45.0, 21.0, 118.4, 0.0, 26.0),
    (42.0, 27.0, 119.0, -0.25, 14.0),
    (43.0, 31.5, 118.7, 0.0, 3.0),
    (48.0, 28.0, 118.7, -1.0, 10.0),
    (44.0, 24.3, 118.0, 0.0, 19.0),
    (47.0, 18.0, 118.4, 0.5, 32.0),
    (40.0, 25.5, 118.9, -2.0, 20.0),
]


def build_cases():
    cases = []
    for AL in AL_GRID:
        for K in K_GRID:
            for A in A_GRID:
                for T in T_GRID:
                    Ps = [10.0, 20.0, 30.0]
                    cases.append({"K": K, "AL": AL, "A": A, "T": T, "P": Ps,
                                  "app": expected(K, AL, A, T, Ps, "app"),
                                  "excel": expected(K, AL, A, T, Ps, "excel"),
                                  "iolsolver": expected(K, AL, A, T, Ps, "iolsolver")})
    return cases


def build_selftest():
    out = []
    for K, AL, A, T, P in SELFTEST_INPUTS:
        e = expected(K, AL, A, T, [P], "app")
        out.append({"K": K, "AL": AL, "A": A, "T": T, "P": P,
                    "expect": {fid: {"emme": round(v["emme"], 6), "forTarget": round(v["forTarget"], 6), "rx": round(v["rx"][0], 6)}
                               for fid, v in e.items()}})
    return out


def inject_selftest(selftest, html_path):
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(selftest, separators=(",", ":"))
    new, n = re.subn(r"/\*SELFTEST_START\*/.*?/\*SELFTEST_END\*/",
                     lambda m: "/*SELFTEST_START*/" + payload + "/*SELFTEST_END*/", html, flags=re.S)
    if n != 1:
        raise SystemExit("SELFTEST markers not found exactly once")
    with open(html_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)


if __name__ == "__main__":
    cases = build_cases()
    with open(os.path.join(HERE, "reference_cases.json"), "w", encoding="utf-8") as f:
        json.dump(cases, f)
    st = build_selftest()
    inject_selftest(st, os.path.join(ROOT, "app", "index.html"))
    print(f"reference cases: {len(cases)}  self-test cases injected: {len(st)}")
    for c in st:
        print(c["K"], c["AL"], c["A"], c["T"], {k: round(v["forTarget"], 2) for k, v in c["expect"].items()})
