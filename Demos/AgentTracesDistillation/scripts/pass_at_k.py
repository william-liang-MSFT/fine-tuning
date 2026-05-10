#!/usr/bin/env python
"""Aggregate multi-pass eval results into pass@k metrics.

Reads result files of the form:
    results/baseline__mt__{role}__{model}.{prefix}pass{N}.json
where role in {student, teacher, ft}.

Each result file has:
    {"results": [ {"id": "T01", "combined_score": 0.85, ...}, ... ]}

pass@k is the standard HumanEval-style estimator: fraction of scenarios where,
across k uniformly-sampled passes from the available N passes, at least one
attempt clears the success threshold tau.

  pass@k_per_scenario = 1 - C(N - C_solved, k) / C(N, k)

Average over scenarios.

Also reports the simpler "mean per-pass success rate" (== pass@1 closed-form).

Usage:
    python scripts/pass_at_k.py --suffix-prefix heldout. --tau 0.70
    python scripts/pass_at_k.py --tau 0.70                  # full-30 default
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

NB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = NB_DIR / "results"


def load_role(role: str, suffix_prefix: str = ""):
    pattern = str(RESULTS_DIR / f"baseline__mt__{role}__*.{suffix_prefix}pass*.json")
    files = sorted(glob.glob(pattern))
    pass_re = re.compile(rf"\.{re.escape(suffix_prefix)}pass(\d+)\.json$")
    by_pass = {}
    for f in files:
        if not suffix_prefix:
            # When no prefix, exclude files that have a known prefix in their suffix
            tail = Path(f).name
            if re.search(r"\.[a-zA-Z][a-zA-Z0-9_]*\.pass\d+\.json$", tail):
                continue
        m = pass_re.search(f)
        if not m:
            continue
        n = int(m.group(1))
        with open(f) as fh:
            by_pass[n] = json.load(fh)
    return by_pass


def build_solve_matrix(by_pass, tau: float):
    """Return {scenario_id: [solved_pass1, solved_pass2, ...]} aligned to sorted pass numbers."""
    pass_nums = sorted(by_pass.keys())
    solve = defaultdict(lambda: [0] * len(pass_nums))
    for idx, n in enumerate(pass_nums):
        rows = by_pass[n].get("per_scenario") or by_pass[n].get("results") or []
        for r in rows:
            sid = r.get("scenario_id") or r.get("id")
            if not sid:
                continue
            score = r.get("combined", r.get("combined_score", 0)) or 0
            solve[sid][idx] = 1 if (score >= tau) else 0
    return solve, pass_nums


def pass_at_k(num_solved: int, n: int, k: int) -> float:
    if k > n:
        return float("nan")
    if num_solved == 0:
        return 0.0
    if (n - num_solved) < k:
        return 1.0
    return 1.0 - (math.comb(n - num_solved, k) / math.comb(n, k))


def report(roles, tau, suffix_prefix):
    print(f"\n{'='*70}\npass@k aggregator | tau={tau} | suffix-prefix='{suffix_prefix}'\n{'='*70}")
    role_tables = {}
    n_passes = None
    n_scenarios = None
    for role in roles:
        by_pass = load_role(role, suffix_prefix)
        if not by_pass:
            print(f"  {role:8s}: NO FILES (pattern baseline__mt__{role}__*.{suffix_prefix}pass*.json)")
            continue
        solve, pass_nums = build_solve_matrix(by_pass, tau)
        n = len(pass_nums)
        if n_passes is None:
            n_passes = n
            n_scenarios = len(solve)
        role_tables[role] = (solve, n)
        per_pass_means = []
        for idx, pn in enumerate(pass_nums):
            solved_this_pass = sum(v[idx] for v in solve.values())
            per_pass_means.append(solved_this_pass / max(1, len(solve)))
        mean_pp = sum(per_pass_means) / len(per_pass_means)
        std_pp = (sum((x - mean_pp) ** 2 for x in per_pass_means) / len(per_pass_means)) ** 0.5
        print(
            f"\n  {role:8s} | passes={pass_nums} | n_scenarios={len(solve)}\n"
            f"           per-pass success: {[f'{x:.2%}' for x in per_pass_means]}"
            f"  mean={mean_pp:.2%}  std={std_pp:.2%}"
        )
        # HumanEval-style pass@k (unbiased estimator, sample k from n passes)
        for k in range(1, n + 1):
            vals = [pass_at_k(sum(v), n, k) for v in solve.values()]
            mean = sum(vals) / len(vals)
            print(f"           pass@{k} (HumanEval unbiased): {mean:.2%}")
        # Cumulative-by-pass-index: solved in any of first k passes (matches the
        # user-facing "with k attempts" storyline)
        for k in range(1, n + 1):
            cum = sum(1 for v in solve.values() if any(v[:k]))
            mean = cum / max(1, len(solve))
            print(f"           pass@{k} (cumulative first-k passes): {mean:.2%}")

    if not role_tables:
        return None

    print(f"\n{'-'*70}\nHEADLINE: tau={tau}, n_scenarios={n_scenarios}, n_passes={n_passes}\n{'-'*70}")
    headline = {
        "tau": tau,
        "n_scenarios": n_scenarios,
        "n_passes": n_passes,
        "humaneval": {},
        "cumulative": {},
    }
    for label, fn in [
        ("HumanEval-unbiased (k draws from n passes)",
         lambda solve, n, k: sum(pass_at_k(sum(v), n, k) for v in solve.values()) / max(1, len(solve))),
        ("Cumulative first-k passes (k attempts in order)",
         lambda solve, n, k: sum(1 for v in solve.values() if any(v[:k])) / max(1, len(solve))),
    ]:
        bucket = "humaneval" if "Unbiased" in label or "HumanEval" in label else "cumulative"
        print(f"\n  Definition: {label}")
        for k in (1, 2, 3):
            if k > n_passes:
                continue
            row = {}
            for role in roles:
                if role not in role_tables:
                    continue
                solve, n = role_tables[role]
                row[role] = fn(solve, n, k)
            if not row:
                continue
            s = row.get("student", float("nan"))
            ft = row.get("ft", float("nan"))
            t = row.get("teacher", float("nan"))
            lift = ft - s if not (math.isnan(s) or math.isnan(ft)) else float("nan")
            recovered = (lift / (t - s)) if (not (math.isnan(t) or math.isnan(s)) and (t - s) != 0) else float("nan")
            print(
                f"    pass@{k}:  S={s:.2%}  FT={ft:.2%}  T={t:.2%}  "
                f"|  lift={lift*100:+.1f}pp  |  recovered={recovered:.0%}"
            )
            headline[bucket][f"pass@{k}"] = row
    return headline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau", type=float, default=0.70)
    ap.add_argument("--suffix-prefix", default="", help="e.g. 'heldout.' for held-out files")
    ap.add_argument("--out", default=None, help="Write headline JSON here")
    ap.add_argument("--roles", default="student,ft,teacher")
    args = ap.parse_args()
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    headline = report(roles, args.tau, args.suffix_prefix)
    if headline and args.out:
        with open(args.out, "w") as f:
            json.dump(headline, f, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
