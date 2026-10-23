"""Compare LLM batch (batch_1000_llm_20261020) vs deterministic batch
(batch_1000_20261019). Joins on pair (frozenset of names)."""
import json, glob, statistics
from collections import Counter, defaultdict
from pathlib import Path

DET = Path("/app/data/mock_duels/batch_1000_20261019")
LLM = Path("/app/data/mock_duels/batch_1000_llm_20261020")

def load(d):
    out = {}
    for f in sorted(d.glob("duel_*.json")):
        r = json.loads(f.read_text())
        key = frozenset(r["pair"])
        out[key] = r
    return out

det = load(DET)
llm = load(LLM)
print(f"det={len(det)} llm={len(llm)}")

# Method breakdown for LLM batch
methods = Counter(r["method"] for r in llm.values())
print("\nLLM batch methods:", dict(methods))
confs = Counter(str(r.get("confidence")) for r in llm.values())
print("LLM batch confidence:", dict(confs))
dur = sorted(r["duration_s"] for r in llm.values() if r["method"].startswith("llm"))
if dur:
    print(f"LLM-judged durations: n={len(dur)} median={statistics.median(dur):.1f}s mean={statistics.mean(dur):.1f}s p90={dur[int(len(dur)*0.9)]:.1f}s")

# Forced-LLM stomp check
forced = {k: r for k, r in llm.items() if r.get("forced_llm")}
print(f"\nForced-LLM stomp duels: {len(forced)}")
f_agree = 0
for k, r in forced.items():
    d = det.get(k)
    if d and d.get("winner") == r.get("winner"):
        f_agree += 1
print(f"forced-LLM agrees with tier-stomp winner: {f_agree}/{len(forced)}")

# Main phase only (non-forced)
main = {k: r for k, r in llm.items() if not r.get("forced_llm")}
close = {k: r for k, r in main.items() if str(r.get("stratum", "")).startswith("close")}
print(f"\nMain phase: {len(main)}; close strata: {len(close)}")

# Agreement on close matchups where BOTH decided (winner not NJR/None)
both_decided = {}
disagree = []
for k, r in close.items():
    d = det.get(k)
    if not d:
        continue
    lw, dw = r.get("winner"), d.get("winner")
    if lw in (None, "needs_judge_review") or dw in (None, "needs_judge_review"):
        continue
    both_decided[k] = (r, d)
    if lw != dw:
        disagree.append((k, r, d))
print(f"Close, both decided: {len(both_decided)}; agree={len(both_decided)-len(disagree)} disagree={len(disagree)}")
if both_decided:
    print(f"Agreement rate: {(len(both_decided)-len(disagree))/len(both_decided)*100:.1f}%")

# NJR rates
llm_njr = sum(1 for r in close.values() if r.get("winner") in (None, "needs_judge_review"))
det_close = {k: v for k, v in det.items() if str(v.get("stratum", "")).startswith("close")}
det_njr = sum(1 for v in det_close.values() if v.get("winner") in (None, "needs_judge_review"))
print(f"NJR close: LLM {llm_njr}/{len(close)} vs DET {det_njr}/{len(det_close)}")

# Position bias on LLM-decided close duels
a_wins = b_wins = 0
for r in close.values():
    if r["method"].startswith("llm") and r.get("winner") in (r["pair"][0], r["pair"][1]):
        if r["winner"] == r["pair"][0]:
            a_wins += 1
        else:
            b_wins += 1
tot = a_wins + b_wins
print(f"LLM close position: A wins {a_wins}, B wins {b_wins}, A% = {a_wins/tot*100:.1f}% (n={tot})" if tot else "no LLM-decided close duels")

# Stomp stratum agreement (main phase): methods should be tier_stomp with same winner
stomp_main = {k: r for k, r in main.items() if str(r.get("stratum", "")).startswith("stomp")}
s_agree = sum(1 for k, r in stomp_main.items() if det.get(k, {}).get("winner") == r.get("winner"))
print(f"Stomp main-phase winner match vs det: {s_agree}/{len(stomp_main)}")

# Confidence distribution of LLM close decisions
cc = Counter(str(r.get("confidence")) for r in close.values() if r["method"].startswith("llm"))
print("LLM close confidence dist:", dict(cc))

# Dump disagreements for manual review
print("\n=== DISAGREEMENTS (close, both decided) ===")
for k, r, d in disagree:
    print(json.dumps({
        "pair": r["pair"], "stratum": r["stratum"],
        "llm_winner": r.get("winner"), "llm_conf": r.get("confidence"), "llm_method": r["method"],
        "det_winner": d.get("winner"), "det_conf": d.get("confidence"),
        "llm_reason": str((r.get("decision") or {}).get("summary") or (r.get("decision") or {}).get("explanation") or "")[:300] if isinstance(r.get("decision"), dict) else None,
    }, default=str))

# Confidence calibration: LLM agreement with det by LLM confidence bucket
byconf = defaultdict(lambda: [0, 0])
for k, (r, d) in both_decided.items():
    c = str(r.get("confidence"))
    byconf[c][1] += 1
    if r.get("winner") == d.get("winner"):
        byconf[c][0] += 1
print("\nLLM-vs-det agreement by LLM confidence:", {c: f"{a}/{t}" for c, (a, t) in byconf.items()})
# Where LLM abstained (NJR) — what did det say?
llm_njr_keys = [k for k, r in close.items() if r.get("winner") in (None, "needs_judge_review") and r["method"].startswith("llm")]
print(f"LLM NJR duels: {len(llm_njr_keys)}; det winners for those:", [det.get(k, {}).get("winner") for k in llm_njr_keys])
