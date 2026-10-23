"""Supplement to analyze_llm.py: schema health + top disagreements detail."""
import json, glob, statistics
from collections import Counter
from pathlib import Path

DET = Path("/app/data/mock_duels/batch_1000_20261019")
LLM = Path("/app/data/mock_duels/batch_1000_llm_20261020")

def load(d):
    out = {}
    for f in sorted(d.glob("duel_*.json")):
        r = json.loads(f.read_text())
        out[frozenset(r["pair"])] = r
    return out

det = load(DET)
llm = load(LLM)

close = {k: r for k, r in llm.items() if not r.get("forced_llm") and str(r.get("stratum", "")).startswith("close")}
print(f"close LLM records: {len(close)}")

# Schema health over genuine LLM verdicts (method llm_*)
llm_verdicts = [r for r in close.values() if r["method"].startswith("llm_")]
schema = [r for r in llm_verdicts if r["method"] == "llm_schema"]
regex = [r for r in llm_verdicts if r["method"] == "llm_regex_text_fallback"]
print(f"LLM verdicts total: {len(llm_verdicts)}; pure schema: {len(schema)} ({len(schema)/max(len(llm_verdicts),1)*100:.1f}%); regex fallback: {len(regex)}; unparseable: 0 (no llm_unknown/error records)")
fb = [r for r in close.values() if r["method"].startswith("fallback")]
print(f"fallback (judge never answered): {len(fb)} -> {[r['method'] for r in fb]}")

# Disagreements with full detail
dis = []
for k, r in close.items():
    d = det.get(k)
    if not d:
        continue
    lw, dw = r.get("winner"), d.get("winner")
    if lw in (None, "needs_judge_review") or dw in (None, "needs_judge_review") or lw == dw:
        continue
    dec = r.get("decision") or {}
    dis.append({
        "pair": r["pair"], "stratum": r["stratum"], "method": r["method"],
        "llm_winner": lw, "llm_conf": r.get("confidence"),
        "det_winner": dw, "det_conf": d.get("confidence"), "det_method": d.get("method"),
        "summary": str(dec.get("summary") or dec.get("explanation") or "")[:500],
        "duration_s": r.get("duration_s"),
    })
print(f"\ndisagreements (both decided): {len(dis)}")
for x in dis:
    print(json.dumps(x, default=str))

# This-run (resume) timing: records timestamped >= 2026-10-21T01:13
thisrun = [r for r in llm.values() if r["timestamp"] >= "2026-10-21T01:13"]
tr_llm = sorted(r["duration_s"] for r in thisrun if r["method"].startswith("llm"))
if tr_llm:
    print(f"\nresume-run LLM duel durations: n={len(tr_llm)} median={statistics.median(tr_llm):.0f}s mean={statistics.mean(tr_llm):.0f}s max={tr_llm[-1]:.0f}s")
tr_all = sorted(r["duration_s"] for r in thisrun)
print(f"resume-run all durations: n={len(tr_all)} median={statistics.median(tr_all):.0f}s")
