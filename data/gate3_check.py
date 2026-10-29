import json
p = json.load(open("/app/data/recovery_progress.json"))
for rel in ("profiles/needs_review/recentchanges/unknown/leafling.yaml",
            "profiles/needs_review/recentchanges/unknown/netskie.yaml",
            "profiles/needs_review/recentchanges/unknown/sheary.yaml"):
    e = p.get(rel) or {}
    print(f"{rel.split('/')[-1]}: recovered={e.get('recovered_fields')} "
          f"identity_mismatch={e.get('identity_mismatch')} "
          f"error={e.get('error')!r} "
          f"blockers_before={e.get('blockers_before')} "
          f"blockers_after={e.get('blockers_after')} "
          f"sources_tried={e.get('sources_tried')}")
print("GATE3-CHECK DONE")
