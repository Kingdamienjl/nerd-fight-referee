import json, glob, collections, statistics

files = sorted(glob.glob("/app/data/mock_duels/batch_1000_20261019/duel_*.json"))
recs = [json.load(open(f)) for f in files]
print(f"N={len(recs)}")

methods = collections.Counter(r["method"].split(":")[0] for r in recs)
print("METHODS:", dict(methods))
methods_full = collections.Counter(r["method"] for r in recs)
print("METHODS_FULL:", dict(methods_full))

conf = collections.Counter(str(r.get("confidence")) for r in recs)
print("CONFIDENCE:", dict(conf))

durs = [r["duration_s"] for r in recs]
print(f"DURATION mean={statistics.mean(durs):.2f}s median={statistics.median(durs):.2f}s max={max(durs):.2f}s total={sum(durs):.0f}s")

no_winner = [r for r in recs if not r.get("winner")]
print(f"NO_WINNER: {len(no_winner)}")

# position bias
def pos_stats(sub, label):
    if not sub: return
    wa = sum(1 for r in sub if r.get("winner") == r["pair"][0])
    print(f"POS {label}: n={len(sub)} winner_is_contender_A={wa} ({100*wa/len(sub):.1f}%)")
pos_stats(recs, "ALL")
pos_stats([r for r in recs if r["method"]=="tier_stomp"], "STOMP")
pos_stats([r for r in recs if r["method"].startswith("deterministic")], "DET_CLOSE")

# stomp correctness: winner must be higher tier
bad_stomp = []
for r in recs:
    if r["method"] != "tier_stomp": continue
    hi = 0 if r["tier_score"][0] > r["tier_score"][1] else 1
    if r.get("winner") != r["pair"][hi]:
        bad_stomp.append(r)
print(f"STOMP_WRONG_WINNER: {len(bad_stomp)}")

# close duels: does deterministic engine pick higher tier?
close = [r for r in recs if r["method"].startswith("deterministic")]
agree = disagree = tie = 0
upsets = []
for r in close:
    if r["tier_score"][0] == r["tier_score"][1]:
        tie += 1; continue
    hi = 0 if r["tier_score"][0] > r["tier_score"][1] else 1
    if r.get("winner") == r["pair"][hi]: agree += 1
    else:
        disagree += 1
        if r["tier_gap"] >= 0.75: upsets.append(r)
print(f"CLOSE: agree_with_tier={agree} disagree={disagree} exact_tier_tie={tie} (of {len(close)})")
print(f"CLOSE_UPSETS (gap>=0.75, lower tier won): {len(upsets)}")
for r in upsets[:8]:
    print(f"  UPSET {r['pair'][0]}({r['tier'][0]}) vs {r['pair'][1]}({r['tier'][1]}) gap={r['tier_gap']} -> {r.get('winner')} conf={r.get('confidence')}")

# franchise win rates
apps = collections.Counter(); wins = collections.Counter()
for r in recs:
    if not r.get("winner"): continue
    for i in (0,1):
        apps[r["franchise"][i]] += 1
    wi = 0 if r["winner"] == r["pair"][0] else 1
    wins[r["franchise"][wi]] += 1
fr = [(f, wins[f], apps[f], wins[f]/apps[f]) for f in apps if apps[f] >= 30]
fr.sort(key=lambda x: -x[3])
print("FRANCHISE WIN% (n>=30 apps):")
for f, w, a, p in fr:
    print(f"  {f}: {w}/{a} = {100*p:.0f}%")

# confidence by stratum
for s in sorted(set(r["stratum"] for r in recs)):
    sub = [r for r in recs if r["stratum"] == s]
    c = collections.Counter(str(r.get("confidence")) for r in sub)
    print(f"STRATUM {s}: n={len(sub)} conf={dict(c)}")
