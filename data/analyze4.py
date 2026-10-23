import json, glob

files = sorted(glob.glob("/app/data/mock_duels/batch_1000_20261019/duel_*.json"))
recs = [json.load(open(f)) for f in files]

for r in recs:
    names = set(r["pair"])
    if names == {"Silver Surfer", "Alucard"} or names == {"Raiden", "Master Roshi"}:
        d = r["decision"]
        print("="*70)
        print(f"PAIR: {r['pair']} | index tiers: {r['tier']} scores={r['tier_score']} gap={r['tier_gap']} | method={r['method']} winner={r.get('winner')}")
        print("SUMMARY:", str(d.get("summary"))[:400])
        print("DECIDING:", json.dumps(d.get("deciding_factors"), default=str)[:400])
        diag = d.get("diagnostics") or {}
        print("DIAG tier fields:", {k: v for k, v in diag.items() if "tier" in k.lower()})

# the deterministic duel in stomp stratum
for r in recs:
    if r["stratum"] == "stomp_4.0-6.0" and r["method"].startswith("deterministic"):
        print("="*70)
        print(f"DET-IN-STOMP: {r['pair']} index tiers {r['tier']} scores={r['tier_score']} gap={r['tier_gap']} -> {r.get('winner')} conf={r.get('confidence')}")
