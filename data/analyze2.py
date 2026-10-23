import json, glob, collections, statistics

files = sorted(glob.glob("/app/data/mock_duels/batch_1000_20261019/duel_*.json"))
recs = [json.load(open(f)) for f in files]

# 1. needs_judge_review count
njr = [r for r in recs if r.get("winner") == "needs_judge_review"]
print(f"NEEDS_JUDGE_REVIEW: {len(njr)}")
print("  NJR by stratum:", dict(collections.Counter(r["stratum"] for r in njr)))

# 2. bad stomps detail
print("\n--- BAD STOMPS ---")
for r in recs:
    if r["method"] != "tier_stomp": continue
    hi = 0 if r["tier_score"][0] > r["tier_score"][1] else 1
    if r.get("winner") != r["pair"][hi]:
        print(f"  {r['pair'][0]}({r['tier'][0]}) vs {r['pair'][1]}({r['tier'][1]}) gap={r['tier_gap']} -> winner={r.get('winner')}")

# 3. low-conf stomp
print("\n--- LOW-CONF STOMP ---")
for r in recs:
    if r["method"]=="tier_stomp" and r.get("confidence")=="low":
        print(f"  {r['pair'][0]}({r['tier'][0]}) vs {r['pair'][1]}({r['tier'][1]}) gap={r['tier_gap']} -> {r.get('winner')}")

# 4. High-conf in close strata
print("\n--- HIGH-CONF CLOSE ---")
for r in recs:
    if r["method"].startswith("deterministic") and r.get("confidence") in ("High","strong"):
        print(f"  {r['pair'][0]}({r['tier'][0]}) vs {r['pair'][1]}({r['tier'][1]}) gap={r['tier_gap']} -> {r.get('winner')} conf={r.get('confidence')}")

# 5. franchise: avg tier of fighter vs avg tier of opponents
print("\n--- FRANCHISE TIER CHECK ---")
ft = collections.defaultdict(list); fo = collections.defaultdict(list)
for r in recs:
    for i in (0,1):
        ft[r["franchise"][i]].append(r["tier_score"][i])
        fo[r["franchise"][i]].append(r["tier_score"][1-i])
for f in ["Final Fantasy","God of War","Dragon Ball","JoJo's Bizarre Adventure","Jujutsu Kaisen","Mortal Kombat","Marvel"]:
    if ft[f]:
        print(f"  {f}: n={len(ft[f])} avg_own_tier_score={statistics.mean(ft[f]):.2f} avg_opp_tier_score={statistics.mean(fo[f]):.2f}")

# 6. position bias by stratum for deterministic
print("\n--- DET POS BIAS BY STRATUM ---")
for s in sorted(set(r["stratum"] for r in recs if r["method"].startswith("deterministic"))):
    sub = [r for r in recs if r["stratum"]==s and r["method"].startswith("deterministic")]
    wa = sum(1 for r in sub if r.get("winner")==r["pair"][0])
    wb = sum(1 for r in sub if r.get("winner")==r["pair"][1])
    nj = sum(1 for r in sub if r.get("winner")=="needs_judge_review")
    print(f"  {s}: n={len(sub)} A={wa} B={wb} NJR={nj}")

# 7. winner_probability sanity
wps = [r["winner_probability"] for r in recs if isinstance(r.get("winner_probability"), (int,float))]
print(f"\nWINNER_PROB: n={len(wps)} min={min(wps):.3f} max={max(wps):.3f} median={statistics.median(wps):.3f}" if wps else "\nWINNER_PROB: none numeric")
# deterministic close: does winner match engine_verdict?
mm = sum(1 for r in recs if r["method"].startswith("deterministic") and (r.get("engine_verdict") or {}).get("winner") != r.get("winner"))
print(f"DET engine_verdict!=winner: {mm}")
