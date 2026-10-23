import json, glob, random, collections

files = sorted(glob.glob("/app/data/mock_duels/batch_1000_20261019/duel_*.json"))
recs = [json.load(open(f)) for f in files]
rng = random.Random(42)

def axis_agree(r):
    ab = r.get("advantage_breakdown") or {}
    axes = [v for v in ab.values() if isinstance(v, dict) and v.get("winner")]
    if not axes: return None
    agree = sum(1 for v in axes if v["winner"] == r.get("winner"))
    return agree, len(axes)

for label, confilter in [("STRONG", lambda r: r.get("confidence")=="strong"),
                          ("LOW", lambda r: r.get("confidence")=="low"),
                          ("MEDIUM", lambda r: r.get("confidence")=="medium")]:
    pool = [r for r in recs if r["method"].startswith("deterministic") and confilter(r) and r.get("winner") not in (None,"needs_judge_review")]
    sample = rng.sample(pool, min(20, len(pool)))
    full = partial = 0; details = []
    for r in sample:
        aa = axis_agree(r)
        if aa:
            agree, tot = aa
            if agree == tot: full += 1
            elif agree > tot/2: partial += 1
            details.append((r["pair"][0], r["pair"][1], r.get("winner"), f"{agree}/{tot}"))
    print(f"{label}: pool={len(pool)} sampled={len(sample)} all_axes_agree={full} majority_agree={partial}")
    for d in details[:5]:
        print(f"    {d[0]} vs {d[1]} -> {d[2]} axes {d[3]}")

# low-conf: how many are NJR vs decided?
low = [r for r in recs if r.get("confidence")=="low"]
print(f"\nLOW total={len(low)} NJR={sum(1 for r in low if r.get('winner')=='needs_judge_review')} decided={sum(1 for r in low if r.get('winner') not in (None,'needs_judge_review'))}")

# data-quality: franchise/name mismatches (heuristic)
suspects = []
for r in recs:
    for i in (0,1):
        nm, fr = r["pair"][i], r["franchise"][i]
        if ("Gohan" in nm or "Deadpool" in nm or "Cell" in nm) and fr in ("Marvel","DC","Marvel Comics"):
            suspects.append((nm, fr))
print("NAME/FRANCHISE SUSPECTS:", collections.Counter(suspects).most_common(8))
