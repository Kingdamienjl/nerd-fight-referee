"""Frag-13 implementation patch (run on the box): add H1/H2/H5 screens
to auto_repair.py and H-tests to tests/test_recovery_guard.py.
Fails loudly if any anchor is missing or ambiguous. Idempotent-safe:
refuses to run twice (checks for the H markers first).
"""
import sys

AR = "/opt/referee/src/battlebot/review/auto_repair.py"
TEST = "/opt/referee/tests/test_recovery_guard.py"

ar = open(AR).read()
if "footer_instruction" in ar:
    print("ABORT: H screens already present in auto_repair.py")
    sys.exit(1)

H_BLOCK = '''# ---------------------------------------------------------------------------
# Frag-13 (H-series) screens: the expand-gate H1/H2 merges + the
# uncovered quarantined verbatim items. Calibration:
# /opt/referee/data/frag13_20261027/frag13_calib{1,2,3}.py
# (8,376 profiles / 174,710 items, current code).
#   H1 footer_instruction: the vsbattles footer sentence merged as a
#      weakness ("etc. You can judge a person's power by their
#      feats."). Item level: raw 15, already-caught 14 (via the
#      template tail), residual 1 (son-goku-ultra-instinct-sign bare
#      sentence). All 15 genuine footer debris, zero legit items.
#      Line level: 53 files / 112 lines (the Oct 26 report's 147/314
#      predates drain/intake churn); most occurrences live in
#      field_candidates `value:` records, not list items -- the screen
#      guards the merge path, it does not clean stored files.
#   H2 editor_note_unfinished: the Animal Man editor note ("This
#      profile is so far from done but i am sleepy (Last issue
#      recorded Issue #14 of Animal Man 1988)"), merged as an ability
#      on animal-man-rebirth in the expand run. clean_item_tails only
#      strips "Note:" markers / "before making any changes", so this
#      note escapes it. Corpus: 34 lines, all the same note in both
#      forms ("This profile is..." standalone, "This is..." glued onto
#      real prose); zero legit occurrences in 174,710 items. The
#      screen keys on "so far from done" so both forms and line-wrapped
#      copies are caught.
#   H5 episode_hyphen_title: episode/chapter label + hyphen + real
#      title ("Episode 2 - I'll Give You The Grand Tour",
#      "Episode 7 - Don't Do Anything Rash"). G1's label-title rule
#      covers colon/dot separators only; the hyphen form escapes it
#      when the title runs past the <=2-prose-word prefix rule.
#      Item level: raw 15, already-caught 9, residual 6, all genuine.
#      (The omni-man Episode 2/7 titles exist in the corpus only
#      glued to following prose -- "Episode 2 - I'll Give You The
#      Grand Tour A refined bioactive compound from..." -- a G7 glue
#      composite, kept; the bare-form coverage is forward-looking for
#      the next splitter output.)
#      Title words are matched case-insensitively because real episode
#      titles contain lowercase function words ("A New Kind of Fear");
#      the label+number+hyphen anchor is the debris signal, and the
#      <=6-word title cap keeps long prose out.
#   NO CODE (calibrated, documented):
#   H3a as-led subordinate clause ("as the scenes depicting Ronova
#      permanently killing living beings"): the verbless-as rule's
#      residual is 74, mostly legit ("as well as to Sleep
#      Manipulation", "as a magi", "As a robot").
#   H3b participial clause ("Rhinedottir freely creating life",
#      "and Asmoday creating numerous worlds within her pocket
#      space"): broad rule residual 196 with legit FPs ("Incomplete
#      training", "Aura sensing"); the verb-blocklist variant has zero
#      corpus presence (the target shards do not exist as stored item
#      names -- they are comma-splits of one long stored claims
#      passage), so it is untestable. The asmoday/ronova profiles
#      refuse at identity, so the shards cannot re-merge; manual audit
#      stays the backstop.
#   H4 bare series name ("The Boys"): residual 75, of which 73 are
#      legit equipment ("The Elessar", "The Elendilmir", "The Colt")
#      against 2 "The Boys" -- needs franchise context, as frag-12
#      concluded. Manual audit stays the backstop.
# ---------------------------------------------------------------------------

_FOOTER_INSTRUCTION_RE = re.compile(
    r"(?i)you can judge a person['\\u2019]s power by their feats"
)
_EDITOR_NOTE_UNFINISHED_RE = re.compile(r"(?i)so far from done")
_EPISODE_HYPHEN_RE = re.compile(
    r"(?i)^\\s*(?:chapter|act|scene|part|volume|book|season|episode)\\s+"
    r"(?:[ivxlcdm]+|[0-9]+)\\s*[-\\u2013\\u2014]\\s+"
    r"[A-Z][\\w'\\u2019-]*(?:\\s+[A-Z][\\w'\\u2019-]*){0,5}\\s*\\.?\\s*$"
)


def _footer_instruction(value: str) -> bool:
    """H1: the wiki-footer instructional sentence filed as a list item
    ("etc. You can judge a person's power by their feats.")."""
    return bool(_FOOTER_INSTRUCTION_RE.search(str(value or "")))


def _editor_note_unfinished(value: str) -> bool:
    """H2: an editor's unfinished-profile note filed as a list item
    ("This profile is so far from done but i am sleepy...")."""
    return bool(_EDITOR_NOTE_UNFINISHED_RE.search(str(value or "")))


def _episode_hyphen_title(value: str) -> bool:
    """H5: a series/season/episode/chapter/act label + hyphen + real
    title as a list item ("Episode 2 - I'll Give You The Grand Tour").
    The colon/dot form is already caught by _label_fragment."""
    return bool(_EPISODE_HYPHEN_RE.match(str(value or "").strip()))


'''

anchor_fn = "def fragment_item_reasons(item: Any, *, section: str | None = None) -> list[str]:"
assert ar.count(anchor_fn) == 1, "fragment_item_reasons anchor not unique"
ar = ar.replace(anchor_fn, H_BLOCK + anchor_fn, 1)

anchor_wire = '''    if section == "weaknesses" and _capability_in_weaknesses(value, lowered):
        reasons.append("capability_in_weaknesses")
    return reasons'''
assert ar.count(anchor_wire) == 1, "wire anchor not unique"
wire = '''    if section == "weaknesses" and _capability_in_weaknesses(value, lowered):
        reasons.append("capability_in_weaknesses")
    if _footer_instruction(value):
        reasons.append("footer_instruction")
    if _editor_note_unfinished(value):
        reasons.append("editor_note_unfinished")
    if _episode_hyphen_title(value):
        reasons.append("episode_hyphen_title")
    return reasons'''
ar = ar.replace(anchor_wire, wire, 1)
open(AR, "w").write(ar)
print("auto_repair.py patched")

test = open(TEST).read()
if "Frag13ScreenTests" in test:
    print("ABORT: H tests already present in test_recovery_guard.py")
    sys.exit(1)

H_TESTS = '''

class ThirteenthGenFrag13ScreenTests(unittest.TestCase):
    """Frag-13 workstream: the expand-gate H1/H2 merges + the uncovered
    quarantined verbatim items.

    Verbatim items come from the expand-gate revert
    (/opt/referee/data/expand_20261025/) and the calibration rounds
    (/opt/referee/data/frag13_20261027/frag13_calib{1,2,3}.py:
    8,376 profiles / 174,710 items). Controls are the legit items
    calibration showed must survive.
    """

    # -- H1 footer instructional sentence -------------------------------
    def test_footer_instruction_verbatim(self):
        for item in (
            "etc. You can judge a person's power by their feats.",
            "etc. You can judge a person's power by their feats. "
            "Notable Attacks/Techniques: A list of some abilities "
            "the character has",
        ):
            self.assertIn(
                "footer_instruction",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    def test_footer_instruction_controls_survive(self):
        # The exact footer sentence is the signal; looser "judge by
        # feats" phrasing is real prose and passes.
        for item in (
            "You can judge his power by his feats in battle.",
            "Feats determine a character's power level.",
            "His strength is judged by his victories.",
        ):
            self.assertNotIn(
                "footer_instruction", fragment_item_reasons(item), item
            )

    # -- H2 unfinished-profile editor note ------------------------------
    def test_editor_note_unfinished_verbatim(self):
        for item in (
            "This profile is so far from done but i am sleepy "
            "(Last issue recorded Issue #14 of Animal Man 1988)",
            "A powerful mage whom in his regular form could combat "
            "Nezha) This is so far from done but i am sleepy "
            "(Last issue recorded Issue #14 of Animal Man 1988)",
        ):
            self.assertIn(
                "editor_note_unfinished",
                fragment_item_reasons(item, section="abilities"),
                item,
            )

    def test_editor_note_unfinished_controls_survive(self):
        for item in (
            "He has not finished his training.",
            "His technique is incomplete.",
            "His mastery is far from complete.",
        ):
            self.assertNotIn(
                "editor_note_unfinished",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    # -- H5 episode title, hyphen separator ----------------------------
    def test_episode_hyphen_title_verbatim(self):
        for item in (
            "Episode 2 - I'll Give You The Grand Tour",
            "Episode 7 - Don't Do Anything Rash",
            "Chapter 6 - A New Kind of Fear",
            "Chapter 5 - An Unexpected StrengthDragon Ball Z",
            "Act 11 - Reunion",
        ):
            self.assertIn(
                "episode_hyphen_title", fragment_item_reasons(item), item
            )

    def test_episode_hyphen_title_controls_survive(self):
        # Colon form is G1's, not H5's; a label glued to substantive
        # prose is kept; a title past the 6-word cap is kept.
        self.assertNotIn(
            "episode_hyphen_title",
            fragment_item_reasons("Episode 2: The Beginning"),
        )
        self.assertNotIn(
            "episode_hyphen_title",
            fragment_item_reasons(
                'Episode 9 "Grievous Intrigue" likely helped by the '
                "unpredictability of this contortion."
            ),
        )
        self.assertNotIn(
            "episode_hyphen_title",
            fragment_item_reasons(
                "Episode 2 - The Long And Winding Road To The Very "
                "Distant Future"
            ),
        )
'''

anchor_main = '\n\nif __name__ == "__main__":\n    unittest.main()\n'
assert test.count(anchor_main) == 1, "test __main__ anchor not unique"
test = test.replace(anchor_main, H_TESTS + anchor_main, 1)
open(TEST, "w").write(test)
print("test_recovery_guard.py patched")
print("PATCH DONE")
