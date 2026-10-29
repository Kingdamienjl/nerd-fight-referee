#!/usr/bin/env python3
"""Frag-11 cohort quarantine #2: item-level revert of the label / header /
wrong-section debris in 7 more profiles' weaknesses (36 items).

Same shape as quarantine #1, now systemic (9 profiles total, >5):
a lore/justification/citation passage was split into weakness items:
  * bare series/season/episode labels ('The Boys', 'Season 1', 'Episode 2',
    'Season 4', 'Episode 8', '"Season Four Finale" Additionally',
    'Episode 2 - ... Grand Tour...', "Episode 7 - Don't Do Anything Rash")
  * list-intro header fragments ('Black Noir has the following',
    'Starlight has the following', 'Stormfront has the following')
  * a whole wrong-section powers passage (steven-universe: ~25 weakness
    items are Shield/Bubble/Shapeshifting ability descriptions; keep
    only the genuine limitation 'he can only do this for a certain amount
    of time and his half-human nature puts more of a strain...')
  * a bare equipment fragment (amethyst: "Amethyst's upgraded whip.")
Kept (real content): omni-man's Sinlak-Beetle item (episode-label prefix
on a real weakness), soldier-boy's invulnerability fragments (true
content, part of the weakness discussion).

Rules (frag-9/10 lessons): do NOT recompute profile_hash; profile_type /
review diff keys are recovery stamps (left alone); progress entries are
updated IN PLACE (add quarantine flags + note, keep everything else --
black-noir and amethyst were promoted in run 5 and their entries record
promoted=True; weaknesses are not part of the eligibility contract).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import service

# (rel, mode, ids): mode "remove" = drop listed ids; "keep_only" = drop all but listed
TARGETS = (
    ("profiles/needs_review/mixed/steven-universe/steven-universe.yaml",
     "keep_only",
     {"weaknesses-he-can-only-do-this-for-a-certain-amount-of-time-and-his-half-human-n"}),
    ("profiles/needs_review/mixed/invincible/omni-man.yaml",
     "remove",
     {"weaknesses-episode-2-i-ll-give-you-the-grand-tourinvincible-season-4",
      "weaknesses-episode-7-don-t-do-anything-rash"}),
    ("profiles/needs_review/mixed/the-boys/soldier-boy.yaml",
     "remove",
     {"weaknesses-the-boys",
      "weaknesses-season-1",
      "weaknesses-episode-2",
      "weaknesses-season-4",
      "weaknesses-episode-8",
      "weaknesses-season-four-finale-additionally"}),
    ("profiles/needs_review/mixed/the-boys/black-noir.yaml",
     "remove",
     {"weaknesses-black-noir-has-the-following"}),
    ("profiles/needs_review/mixed/the-boys/starlight.yaml",
     "remove",
     {"weaknesses-starlight-has-the-following"}),
    ("profiles/needs_review/mixed/the-boys/stormfront.yaml",
     "remove",
     {"weaknesses-stormfront-has-the-following"}),
    ("profiles/needs_review/mixed/steven-universe/amethyst.yaml",
     "remove",
     {"weaknesses-amethyst-s-upgraded-whip"}),
)

progress_path = Path("/app/data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
report = {}
for rel, mode, ids in TARGETS:
    path = Path("/app") / rel
    prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    before = prof.get("weaknesses") or []
    if isinstance(before, dict):
        before = list(before.values())
    if mode == "remove":
        kept = [w for w in before if str((w or {}).get("id") or "") not in ids]
    else:
        kept = [w for w in before if str((w or {}).get("id") or "") in ids]
    removed = [w for w in before if w not in kept]
    prof["weaknesses"] = kept
    with path.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    after = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    after_w = after.get("weaknesses") or []
    if isinstance(after_w, dict):
        after_w = list(after_w.values())
    if mode == "remove":
        still_bad = [w for w in after_w if str((w or {}).get("id") or "") in ids]
    else:
        still_bad = [w for w in after_w if str((w or {}).get("id") or "") not in ids]
    entry = {
        "removed": len(removed),
        "removed_names": [str((w or {}).get("name"))[:60] for w in removed],
        "kept": len(kept),
        "kept_names": [str((w or {}).get("name"))[:60] for w in kept],
        "still_bad_after": len(still_bad),
        "schema_blockers_after": service.schema_validation_blockers(after),
        "approval_blockers_after": service.approval_blockers(after),
        "battle_eligible_after": bool(after.get("battle_eligible")),
        "profile_hash_untouched": True,
    }
    report[rel] = entry
    # update progress entry in place: quarantine flags, keep recorded fields
    ent = progress.get(rel) or {}
    ent["quarantined_frag11"] = True
    ent["quarantine_note"] = ("frag-11 quarantine #2: label/header/wrong-section "
                              "weakness items reverted (%d removed); re-process in "
                              "frag-12 after screen fix" % len(removed))
    progress[rel] = ent
progress_path.write_text(json.dumps(progress, indent=1, sort_keys=True))
print(json.dumps(report, indent=1, ensure_ascii=False))
print("progress_keys_after:", len(progress))
print("QUARANTINE2 DONE")
