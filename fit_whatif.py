#!/usr/bin/env python3
"""Counterfactual PigWeedSAT fit analyses (host packing only; nothing is solved
on PigWeedSAT, no RTL is elaborated, no PigWeedSAT file is modified).

  capacity    Re-run the unchanged host loader (satlat.host.build_images) on
              every original CNF with the design.py capacity constants
              (N_MAX, C_MAX, LE_MAX, CE_MAX) patched in memory.  This counts
              what the *packer* would accept; it does not show that a resized
              design synthesizes, fits block RAM or meets 50 MHz timing.
              Derived field widths and the RTL memories are not re-elaborated.

  preprocess  Simplify every original CNF with the pinned Kissat's initial
              preprocessing only (`--conflicts=0 -o simplified.cnf`, which
              writes the remaining irredundant clauses), compact the variable
              numbering, and run the unchanged loader at the frozen capacities.
              Kissat's elimination/reconstruction stack is not written, so a
              model of the simplified formula is NOT a model of the original.

Usage (from the repository root; PigWeedSAT checked out as ../PigWeedSAT):
  .venv-fpga/bin/python -B fit_whatif.py capacity
  .venv-fpga/bin/python -B fit_whatif.py preprocess
Inputs: calibration/combined_results.csv and the retained (local-only)
calibration/cpu-v0/attempts/<ID>/attempt-001/input.cnf files.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "PigWeedSAT"))
import design as D            # noqa: E402
import satlat.host as H        # noqa: E402

COMBINED = os.path.join(HERE, "calibration", "combined_results.csv")
ATTEMPTS = os.path.join(HERE, "calibration", "cpu-v0", "attempts")
KISSAT = os.path.join(HERE, ".tools", "kissat", "build", "kissat")
TIERS = ("S", "S-tight", "M-low", "M-high")
BASE = {k: getattr(D, k) for k in ("N_MAX", "C_MAX", "LE_MAX", "CE_MAX")}


def load_rows():
    with open(COMBINED, newline="") as f:
        return list(csv.DictReader(f))


def input_path(iid):
    return os.path.join(ATTEMPTS, iid, "attempt-001", "input.cnf")


def accepts(nv, clauses, P, caps=BASE):
    """Loader acceptance plus the fixed-field/stack checks the screen applies."""
    saved = {k: getattr(D, k) for k in caps}
    for k, v in caps.items():
        setattr(D, k, v)
    try:
        img = H.build_images(nv, clauses, H.pigweed(H.Config(lit_page=P)))
    except H.Unsupported:
        return False
    finally:
        for k, v in saved.items():
            setattr(D, k, v)
    longest = max((len(c) for c in clauses), default=0)
    return img.fixed_height <= caps["N_MAX"] and longest < (1 << D.NUM_W)


def ram_bits(caps):
    """Bits in design.Memories.SPEC with depths scaled to `caps` (field widths
    held at today's values, so slightly low for larger caps)."""
    from amaranth.hdl import Shape
    from amaranth.lib import data
    tot = 0
    for name, shape, depth in D.Memories.SPEC:
        w = shape.size if isinstance(shape, data.Layout) else Shape.cast(shape).width
        if name in ("ls", "l2c"):
            depth = depth * caps["LE_MAX"] // BASE["LE_MAX"]
        elif name in ("cs", "c2l"):
            depth = depth * caps["CE_MAX"] // BASE["CE_MAX"]
        elif name in ("cmd", "cst", "used"):
            depth = depth * caps["C_MAX"] // BASE["C_MAX"]
        elif name not in ("rc", "tomin", "mq"):
            depth = depth * caps["N_MAX"] // BASE["N_MAX"]
        tot += w * depth
    return tot


def cmd_capacity(rows):
    parsed = {r["id"]: H.parse_dimacs(input_path(r["id"])) for r in rows}
    cert = {r["id"] for r in rows if r["certified"] == "yes"}
    tier = {r["id"]: r["tier"] for r in rows}
    scen = [("today", BASE),
            ("literal + clause-body stores x2", dict(BASE, LE_MAX=2 * BASE["LE_MAX"], CE_MAX=2 * BASE["CE_MAX"])),
            ("clauses x2, both stores x2", dict(BASE, C_MAX=2 * BASE["C_MAX"], LE_MAX=2 * BASE["LE_MAX"], CE_MAX=2 * BASE["CE_MAX"])),
            ("everything x2", {k: 2 * v for k, v in BASE.items()}),
            ("vars x2, clauses x3, both stores x3", dict(N_MAX=2 * BASE["N_MAX"], C_MAX=3 * BASE["C_MAX"], LE_MAX=3 * BASE["LE_MAX"], CE_MAX=3 * BASE["CE_MAX"])),
            ("everything x4", {k: 4 * v for k, v in BASE.items()})]
    out = []
    for name, caps in scen:
        rec = {"scenario": name, "caps": caps,
               "solver_ram_bits_vs_today": round(ram_bits(caps) / ram_bits(BASE), 2)}
        for P in (16, 8):
            ok = [i for i, (nv, cl) in parsed.items() if accepts(nv, cl, P, caps)]
            t = Counter(tier[i] for i in ok)
            rec[f"P{P}"] = {"accepted": len(ok), "certified": sum(i in cert for i in ok),
                            "by_tier": {x: t[x] for x in TIERS}}
        out.append(rec)
        print(f"{name:38s} P16 {rec['P16']['accepted']:3d} (cert {rec['P16']['certified']:3d})  "
              f"P8 {rec['P8']['accepted']:3d} (cert {rec['P8']['certified']:3d})  P8 by tier {rec['P8']['by_tier']}  "
              f"RAM bits x{rec['solver_ram_bits_vs_today']}")
    store_caps = dict(BASE, LE_MAX=0, CE_MAX=0)
    print(f"share of today's solver RAM bits in the 4 store-sized RAMs (ls, l2c, cs, c2l): "
          f"{1 - ram_bits(store_caps) / ram_bits(BASE):.0%}")
    return out


def compact(path):
    """Read a DIMACS file; renumber the variables that occur to 1..k."""
    clauses, cur = [], []
    with open(path) as f:
        for line in f:
            if not line.strip() or line[0] in "cp":
                continue
            for tok in line.split():
                v = int(tok)
                if v == 0:
                    clauses.append(cur)
                    cur = []
                else:
                    cur.append(v)
    used = sorted({abs(x) for c in clauses for x in c})
    ren = {v: i + 1 for i, v in enumerate(used)}
    return len(used), [[(1 if x > 0 else -1) * ren[abs(x)] for x in c] for c in clauses]


def cmd_preprocess(rows):
    out = []
    with tempfile.TemporaryDirectory() as td:
        for r in rows:
            iid = r["id"]
            simp = os.path.join(td, f"{iid}.cnf")
            try:
                res = subprocess.run([KISSAT, "--seed=0", "--conflicts=0", "-n", "-q", "-o", simp,
                                      input_path(iid)], capture_output=True, text=True, timeout=120)
                code = res.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
            rec = {"id": iid, "tier": r["tier"], "certified": r["certified"],
                   "orig_vars": int(r["variables"]), "orig_clauses": int(r["clauses"]),
                   "kissat_exit": code}
            if code in (10, 20):
                rec["outcome"] = "solved_by_preprocessing_" + ("sat" if code == 10 else "unsat")
            elif code == 0 and os.path.isfile(simp):
                nv, cl = compact(simp)
                rec.update(simp_vars=nv, simp_clauses=len(cl))
                with open(simp, "w") as f:      # re-emit compacted so the host parser sees it
                    f.write(f"p cnf {nv} {len(cl)}\n" + "".join(" ".join(map(str, c)) + " 0\n" for c in cl))
                hv, hcl = H.parse_dimacs(simp)
                rec["P16"] = accepts(hv, hcl, 16)
                rec["P8"] = accepts(hv, hcl, 8)
                rec["outcome"] = "simplified"
            else:
                rec["outcome"] = f"kissat_failed_{code}"
            out.append(rec)
    orig_ok = {r["id"] for r in rows if r["pigweed_P16"] == "loads"}
    simp = [x for x in out if x["outcome"] == "simplified"]
    print("outcomes:", dict(Counter(x["outcome"] for x in out)))
    print(f"accepted after preprocessing: P16 {sum(x['P16'] for x in simp)}  P8 {sum(x['P8'] for x in simp)}  "
          f"(originals accepted at P16: {len(orig_ok)})")
    newly = [x for x in simp if x["P16"] and x["id"] not in orig_ok]
    print("newly accepted at P16 by tier:", dict(Counter(x["tier"] for x in newly)),
          "| of which CPU-certified:", sum(x["certified"] == "yes" for x in newly))
    lost = [x for x in simp if not x["P16"] and x["id"] in orig_ok]
    print("accepted originally but rejected after preprocessing (P16):", [x["id"] for x in lost])
    for t in TIERS:
        sel = [x for x in simp if x["tier"] == t]
        if sel:
            cr = sorted(x["simp_clauses"] / x["orig_clauses"] for x in sel)
            vr = sorted(x["simp_vars"] / x["orig_vars"] for x in sel)
            print(f"{t:8s} median clauses kept {cr[len(cr) // 2]:.0%}, median vars kept {vr[len(vr) // 2]:.0%}, "
                  f"P16 accepted {sum(x['P16'] for x in sel)}/{len(sel)}")
    return out


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("capacity", "preprocess"):
        print(__doc__)
        return 1
    rows = load_rows()
    res = cmd_capacity(rows) if sys.argv[1] == "capacity" else cmd_preprocess(rows)
    out_dir = os.path.join(HERE, "calibration", "whatif-v0")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{sys.argv[1]}.json"), "w") as f:
        json.dump(res, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
