"""Evaluate the user's own spreadsheet formulas at new inputs (Excel semantics, via pycel).

The original workbook is never modified. A temporary copy is made with the Sheet1 input
cells (K, AL, A-constant, IOL power) turned into plain values, then pycel recalculates
the SRK/T (column D), Hoffer Q (column F) and Holladay 1 (column H) formulas.

Usage:  python -X utf8 -I tests/excel_reference.py <scratch_dir>
  writes tests/excel_cases.json
"""
import json
import math
import os
import shutil
import sys

import openpyxl
from pycel import ExcelCompiler

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "Copy of doubleK_계산용_전공의.xlsx")

AL_GRID = [19.0, 20.0, 21.0, 22.0, 23.0, 23.5, 24.0, 24.2, 24.3, 24.4, 24.5, 25.0, 26.0, 27.0, 28.0, 30.0, 32.0]
K_GRID = [39.0, 41.0, 43.5, 45.0, 47.0, 49.0]
A_GRID = [118.0, 118.9]
P_GRID = [15.0, 25.0]

OUT_CELLS = {
    "srkt_LCOR": "D9", "srkt_ELP": "D14", "srkt_emme": "D18", "srkt_rx": "D20",
    "hq_ACD": "F14", "hq_emme": "F18", "hq_rx": "F20",
    "hol_ACD": "H13", "hol_ELP": "H15", "hol_emme": "H18", "hol_rx": "H20",
}


def real(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None  # Excel error (#NUM! etc.) or complex


def main(scratch):
    os.makedirs(scratch, exist_ok=True)
    tmp = os.path.join(scratch, "sheet_copy.xlsx")
    shutil.copyfile(SRC, tmp)
    wb = openpyxl.load_workbook(tmp)
    ws = wb["Sheet1"]
    # Turn the input cell D2 (K, normally from the clinical-history method) into a value.
    ws["D2"] = 43.5
    ws["D4"] = 23.5
    ws["D5"] = 118.0
    ws["D19"] = 20.0
    wb.save(tmp)

    xl = ExcelCompiler(filename=tmp)
    # sanity: the formulas we rely on are present
    for addr in ("D9", "D18", "D20", "F14", "F18", "F20", "H13", "H18", "H20"):
        if not str(openpyxl.load_workbook(tmp)["Sheet1"][addr].value).startswith("="):
            raise SystemExit(f"{addr} is not a formula")

    for addr in OUT_CELLS.values():  # builds pycel's cell map so inputs can be changed
        xl.evaluate(f"Sheet1!{addr}")

    cases = []
    for AL in AL_GRID:
        for K in K_GRID:
            for A in A_GRID:
                row = {"K": K, "AL": AL, "A": A, "P": P_GRID, "out": {}}
                xl.set_value("Sheet1!D2", K)
                xl.set_value("Sheet1!D4", AL)
                xl.set_value("Sheet1!D5", A)
                for i, P in enumerate(P_GRID):
                    xl.set_value("Sheet1!D19", P)
                    for name, addr in OUT_CELLS.items():
                        try:
                            v = real(xl.evaluate(f"Sheet1!{addr}"))
                        except Exception:
                            v = None
                        if name.endswith("_rx"):
                            row["out"].setdefault(name, []).append(v)
                        elif i == 0:
                            row["out"][name] = v
                cases.append(row)
    with open(os.path.join(HERE, "excel_cases.json"), "w", encoding="utf-8") as f:
        json.dump(cases, f)
    n_err = sum(1 for c in cases if c["out"]["srkt_emme"] is None)
    print(f"spreadsheet cases: {len(cases)}  (SRK/T not computable in Excel: {n_err})")
    # sanity check against the values the spreadsheet itself stored (Sheet1 sample eye)
    xl.set_value("Sheet1!D2", 39.604247104247104)
    xl.set_value("Sheet1!D4", 26.0)
    xl.set_value("Sheet1!D5", 118.0)
    xl.set_value("Sheet1!D19", 25.0)
    print("stored-sample check  SRK/T emme %.5f (stored 17.08871)  Rx %.5f (stored -6.48520)  HofferQ emme %.5f (stored 17.77861)"
          % (xl.evaluate("Sheet1!D18"), xl.evaluate("Sheet1!D20"), xl.evaluate("Sheet1!F18")))
    print("Holladay H13 with Excel semantics %.5f (Google Sheets stored -1.21719)" % xl.evaluate("Sheet1!H13"))


if __name__ == "__main__":
    main(sys.argv[1])
