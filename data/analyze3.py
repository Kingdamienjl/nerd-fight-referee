import json, glob, collections, statistics

files = sorted(glob.glob("/app/data/mock_duels/batch_1000_20261019/duel_*.json"))
recs = [json.load(open(f)) for f in files]

# franchise tier check
print("--- FRANCHISE TIER CHECK ---")
ft = collections.defaultdict(list); fo = collections.defaultdict(list)
for r in recs:
    for i in (0,1):
        ft[r["franchise"][i]].append(r["tier_score"][i])
        fo[r["franchise"][i]].append(r["tier_score"][1-i])
for f in ["Final Fantasy","God of War","Dragon Ball","JoJo's Bizarre Adventure","Jujutsu Kaisen","Mortal Kombat","Marvel"]:
    if ft[f]:
        print(f"  {f}: n={len(ft[f])} avg_own={statistics.mean(ft[f]):.2f} avg_opp={statistics.mean(fo[f]):.2f} diff={statistics.mean(ft[f])-statistics.mean(fo[f]):+.2f}")

# det pos bias by stratum
print("\n--- DET POS BIAS BY STRATUM ---")
for s in sorted(set(r["stratum"] for r in recs if r["method"].startswith("deterministic"))):
    sub = [r for r in recs if r["stratum"]==s and r["method"].startswith("deterministic")]
    wa = sum(1 for r in sub if r.get("winner")==r["pair"][0])
    wb = sum(1 for r in sub if r.get("winner")==r["pair"][1])
    nj = sum(1 for r in sub if r.get("winner")=="needs_judge_review")
    print(f"  {s}: n={len(sub)} A={wa} B={wb} NJR={nj}")

# winner_probability
wps = [r["winner_probability"] for r in recs if isinstance(r.get("winner_probability"), (int,float))]
print(f"\nWINNER_PROB: n={len(wps)} min={min(wps):.3f} max={max(wps):.3f} median={statistics.median(wps):.3f}" if wps else "\nWINNER_PROB: none")
# by confidence
for c in ["low","medium","strong"]:
    sub = [r["winner_probability"] for r in recs if r.get("confidence")==c and isinstance(r.get("winner_probability"),(int,float))]
    if sub: print(f"  conf={c}: n={len(sub)} median_prob={statistics.median(sub):.3f}")

# low conf stomp - check exact values
print("\n--- STOMP CONF VALUES ---")
print(collections.Counter(repr(r.get("confidence")) for r in recs if r["method"]=="tier_stomp"))
