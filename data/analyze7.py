import json, glob, collections

files = sorted(glob.glob("/app/data/mock_duels/batch_1000_20261019/duel_*.json"))
recs = [json.load(open(f)) for f in files]

# decided-duel tier agreement by stratum
print("--- DECIDED CLOSE DUELS: tier agreement by stratum ---")
for s in ["close_0.0-0.5","close_0.5-1.0","close_1.0-1.5","close_1.5-2.0"]:
    sub = [r for r in recs if r["stratum"]==s and r.get("winner") in r["pair"]]
    ag = dis = tie = 0
    for r in sub:
        if r["tier_score"][0]==r["tier_score"][1]: tie += 1
        elif r["winner"] == r["pair"][0 if r["tier_score"][0]>r["tier_score"][1] else 1]: ag += 1
        else: dis += 1
    tot = ag+dis
    print(f"  {s}: decided={len(sub)} agree={ag} disagree={dis} tie={tie} agree%={100*ag/tot:.0f}%" if tot else f"  {s}: decided={len(sub)} all ties")

# winner sanity
bad = [r for r in recs if r.get("winner") not in r["pair"] and r.get("winner")!="needs_judge_review"]
print(f"WINNER_NOT_IN_PAIR (excl NJR): {len(bad)}")

# biggest decided upsets by gap (lower tier won, decided)
ups = []
for r in recs:
    if r["method"].startswith("deterministic") and r.get("winner") in r["pair"]:
        wi = 0 if r["winner"]==r["pair"][0] else 1
        if r["tier_score"][wi] < r["tier_score"][1-wi]:
            ups.append((r["tier_gap"], r))
ups.sort(key=lambda x:-x[0])
print("--- BIGGEST DECIDED UPSETS ---")
for g, r in ups[:6]:
    print(f"  gap={g:.2f} {r['pair'][0]}({r['tier'][0]}) vs {r['pair'][1]}({r['tier'][1]}) -> {r['winner']} conf={r.get('confidence')}")

# character win leaderboard (min 5 appearances)
apps = collections.Counter(); wins = collections.Counter()
for r in recs:
    for i in (0,1): apps[r["pair"][i]] += 1
    if r.get("winner") in r["pair"]: wins[r["winner"]] += 1
lb = [(c, wins[c], apps[c]) for c in apps if apps[c] >= 6]
lb.sort(key=lambda x: (-x[1]/x[2], -x[2]))
print("--- MOST APPEARANCES / BEST RECORD (min 6 apps) ---")
for c, w, a in lb[:6]: print(f"  {c}: {w}-{a-w} ({100*w/a:.0f}%)")
print("--- WORST RECORD (min 6 apps) ---")
for c, w, a in lb[-4:]: print(f"  {c}: {w}-{a-w} ({100*w/a:.0f}%)")
print(f"distinct fighters used: {len(apps)}")
