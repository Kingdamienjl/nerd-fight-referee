import json, glob

files = sorted(glob.glob("/app/data/mock_duels/batch_1000_20261019/duel_*.json"))
recs = {tuple(json.load(open(f))["pair"]): json.load(open(f)) for f in files}

targets = [
    ("Hulk (Anime)", "V (Devil May Cry)"),
    ("Ryu", "Satoru Gojo"),
    ("Cell (Post-Crisis)", "Dante"),
    ("Deadpool (DC Comics)", "Menthuthuyoupi"),
    ("Aerith Gainsborough (Final Fantasy)", "Sailor Moon (Eternal)"),
    ("Samus Aran (Varia Suit)", "Yhwach"),
]
for a, b in targets:
    r = recs.get((a,b)) or recs.get((b,a))
    if not r:
        print(f"MISSING {a} vs {b}"); continue
    d = r["decision"]
    print("="*70)
    print(f"{r['pair'][0]}({r['tier'][0]}) vs {r['pair'][1]}({r['tier'][1]}) gap={r['tier_gap']} -> {r.get('winner')} conf={r.get('confidence')} prob={r.get('winner_probability')}")
    print("DECIDING:", json.dumps(d.get("deciding_factors"), default=str)[:600])
    ab = d.get("advantage_breakdown") or {}
    print("ADV:", json.dumps(ab, default=str)[:600])
