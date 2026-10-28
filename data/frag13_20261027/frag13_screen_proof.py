"""Frag-13 screen proof (read-only, local only): run the EXACT merge-path
filter (filter_list_field_items_detailed) on the real H-shape texts that
merged in the expand run, and confirm each is dropped with its H reason
while legit controls are kept. This is the function the recovery runner
calls for every recovered list item.
"""
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review.auto_repair import filter_list_field_items_detailed

CASES = [
    # (label, text, section, expect_dropped_reason_or_None)
    ("H1 bare footer sentence",
     "etc. You can judge a person's power by their feats.",
     "weaknesses", "footer_instruction"),
    ("H1 footer + template tail (the 14 caught form)",
     "etc. You can judge a person's power by their feats. "
     "Notable Attacks/Techniques: A list of some abilities the character has",
     "weaknesses", "footer_instruction"),
    ("H2 editor note standalone",
     "This profile is so far from done but i am sleepy "
     "(Last issue recorded Issue #14 of Animal Man 1988)",
     "abilities", "editor_note_unfinished"),
    ("H2 editor note glued to real prose",
     "A powerful mage (who in his regular form could combat Nezha) "
     "This is so far from done but i am sleepy "
     "(Last issue recorded Issue #14 of Animal Man 1988)",
     "abilities", "editor_note_unfinished"),
    ("H5 episode title, 6-word title",
     "Episode 2 - I'll Give You The Grand Tour",
     "abilities", "episode_hyphen_title"),
    ("H5 episode title, 4-word title",
     "Episode 7 - Don't Do Anything Rash",
     "abilities", "episode_hyphen_title"),
    ("H5 chapter title with lowercase function word",
     "Chapter 6 - A New Kind of Fear",
     "abilities", "episode_hyphen_title"),
    ("CONTROL legit weakness survives",
     "He is vulnerable to high-frequency sounds.",
     "weaknesses", None),
    ("CONTROL legit ability survives",
     "Flight",
     "abilities", None),
    ("CONTROL legit ability prose survives",
     "Energy Manipulation: he can fire blasts of cosmic energy.",
     "abilities", None),
    ("CONTROL 'judge by feats' loose phrasing survives",
     "You can judge his power by his feats in battle.",
     "weaknesses", None),
]

fails = 0
for label, text, section, want in CASES:
    kept, dropped, stripped = filter_list_field_items_detailed(text, section=section)
    reasons = [r for d in dropped for r in d["reasons"]]
    if want is None:
        ok = not dropped and bool(kept.strip())
        status = "PASS" if ok else "FAIL"
        print(f"{status} {label}: kept={kept[:80]!r} dropped={dropped}")
    else:
        ok = want in reasons
        status = "PASS" if ok else "FAIL"
        print(f"{status} {label}: reasons={reasons} kept={kept[:60]!r}")
    if not ok:
        fails += 1
print(f"SCREEN-PROOF {'DONE' if fails == 0 else f'{fails} FAILURES'}")
sys.exit(1 if fails else 0)
