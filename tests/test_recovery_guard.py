"""Unit tests for the Fix A evidence-recovery guard.

Cases are calibrated on the four merges that went wrong in the first
recovery run (Caiman / Yoru / Tai Kamiya / Galatea) plus the fanon-page
shapes that recovered correctly (Korosensei, Shinobu Kocho).
"""

import unittest

from battlebot.review.auto_repair import (
    _guard_name_match,
    boilerplate_reasons,
    evaluate_recovery_guard,
)


def profile(name, franchise, category="anime"):
    return {
        "name": name,
        "franchise": franchise,
        "category": category,
        "identity": {"canonical_name": name, "franchise": franchise, "aliases": []},
        "aliases": [],
        "sources": [],
    }


def verdict(prof, source_title, fetched_title, *, origin="", categories=(), wikitext="", url=""):
    source = {"id": "src", "title": source_title, "url": url or f"https://vsbattles.fandom.com/wiki/{source_title.replace(' ', '_')}"}
    fields = {"origin": origin} if origin else {}
    metadata = {
        "title": fetched_title,
        "url": url or f"https://vsbattles.fandom.com/wiki/{fetched_title.replace(' ', '_')}",
        "revision_id": "123",
        "raw_content": wikitext,
        "fetch_status": "fetched",
    }
    return evaluate_recovery_guard(prof, source, fields, metadata, categories=list(categories))


class NameMatchTests(unittest.TestCase):
    def test_same_name_other_franchise_still_name_matches(self):
        # Franchise evidence, not the name check, must reject these.
        self.assertTrue(_guard_name_match(profile("Yoru", "Chainsaw Man"), "Yoru (Valorant)"))
        self.assertTrue(_guard_name_match(profile("Galatea", "Claymore"), "Galatea (DCAU)"))

    def test_wrong_character_rejected(self):
        self.assertFalse(_guard_name_match(profile("Yoru", "Chainsaw Man"), "Denji (Canon)/Soda727"))
        self.assertFalse(_guard_name_match(profile("Galatea", "Claymore"), "Teresa (Claymore)"))
        self.assertFalse(_guard_name_match(profile("Caiman", "Dorohedoro"), "Kaimen"))
        self.assertFalse(_guard_name_match(profile("Caiman", "Dorohedoro"), "Yacare Caiman"))

    def test_composite_partner_page_rejected(self):
        tai = profile("Tai Kamiya", "Digimon")
        self.assertFalse(_guard_name_match(tai, "Agumon (Taichi Yagami)"))
        self.assertFalse(_guard_name_match(tai, "Taichi Yagami & Agumon(Canon, Digimon Adventure)"))

    def test_fanon_canon_suffix_accepted(self):
        self.assertTrue(
            _guard_name_match(
                profile("Korosensei", "Assassination Classroom"),
                "Korosensei (Canon)/Komodo25M",
            )
        )
        self.assertTrue(
            _guard_name_match(
                profile("Shinobu Kocho", "Demon Slayer"),
                "Shinobu Kocho (Canon, Kimetsu no Yaiba)/Amaterasu",
            )
        )

    def test_direct_and_disambiguated_titles_accepted(self):
        self.assertTrue(_guard_name_match(profile("Caiman", "Dorohedoro"), "Caiman (Dorohedoro)"))
        self.assertTrue(_guard_name_match(profile("Yoru", "Chainsaw Man"), "Yoru (Chainsaw Man)"))
        self.assertTrue(_guard_name_match(profile("Korosensei", "Assassination Classroom"), "Korosensei"))


class GuardVerdictTests(unittest.TestCase):
    def test_valorant_yoru_rejected_no_franchise_evidence(self):
        result = verdict(
            profile("Yoru", "Chainsaw Man"),
            "Yoru",
            "Yoru (Valorant)",
            origin="Valorant",
            categories=["Valorant", "Game Characters", "Tier 9"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("franchise_no_evidence", result["reasons"])
        self.assertTrue(result["name_match"])
        self.assertEqual(result["via"], "search_substitution")

    def test_dcau_galatea_rejected_no_franchise_evidence(self):
        result = verdict(
            profile("Galatea", "Claymore"),
            "Galatea",
            "Galatea (DCAU)",
            origin="DC Animated Universe",
            categories=["DC Animated Universe", "Kryptonians", "Clones"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("franchise_no_evidence", result["reasons"])

    def test_animal_caiman_rejected_name_and_nonfiction(self):
        result = verdict(
            profile("Caiman", "Dorohedoro"),
            "Caiman",
            "Yacare Caiman",
            origin="The Real World",
            categories=["Real World", "Animals", "Reptiles", "Characters"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("name_mismatch", result["reasons"])
        self.assertIn("nonfiction:real_world_category", result["reasons"])
        self.assertIn("nonfiction:real_world_origin", result["reasons"])

    def test_teresa_for_galatea_rejected_name_despite_franchise(self):
        result = verdict(
            profile("Galatea", "Claymore"),
            "Galatea (Claymore)",
            "Teresa (Claymore)",
            origin="Claymore",
            categories=["Claymore", "Characters"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("name_mismatch", result["reasons"])

    def test_good_direct_page_accepted(self):
        result = verdict(
            profile("Caiman", "Dorohedoro"),
            "Caiman (Dorohedoro)",
            "Caiman (Dorohedoro)",
            origin="Dorohedoro",
            categories=["Dorohedoro", "Characters", "Manga Characters"],
        )
        self.assertTrue(result["accepted"], result["reasons"])
        self.assertEqual(result["via"], "recorded_title")

    def test_fanon_substitution_accepted_on_strong_origin_channel(self):
        koro = verdict(
            profile("Korosensei", "Assassination Classroom"),
            "Korosensei (Assassination Classroom)",
            "Korosensei (Canon)/Komodo25M",
            origin="Assassination Classroom",
            categories=["Komodo25M", "Tier 5"],
        )
        self.assertTrue(koro["accepted"], koro["reasons"])
        self.assertEqual(koro["via"], "search_substitution")
        self.assertIn("origin", koro["franchise_channels"])

        shinobu = verdict(
            profile("Shinobu Kocho", "Demon Slayer"),
            "Shinobu Kocho (Demon Slayer)",
            "Shinobu Kocho (Canon, Kimetsu no Yaiba)/Amaterasu",
            origin="Demon Slayer (Kimetsu no Yaiba)",
            categories=[],
        )
        self.assertTrue(shinobu["accepted"], shinobu["reasons"])

    def test_weak_channel_only_substitution_rejected(self):
        result = verdict(
            profile("Yoru", "Chainsaw Man"),
            "Yoru (Chainsaw Man)",
            "Yoru (Canon)/SomeUser",
            origin="",
            categories=[],
            wikitext="A page that name-drops Chainsaw Man in passing.",
        )
        self.assertFalse(result["accepted"])
        self.assertIn("franchise_weak_evidence_only", result["reasons"])

    def test_wikipedia_domain_rejected_for_fictional_profile(self):
        result = verdict(
            profile("Caiman", "Dorohedoro"),
            "Caiman",
            "Caiman",
            origin="Dorohedoro",
            categories=["Dorohedoro"],
            url="https://en.wikipedia.org/wiki/Caiman",
        )
        self.assertFalse(result["accepted"])
        self.assertIn("nonfiction:wikipedia_domain", result["reasons"])


class BoilerplateTests(unittest.TestCase):
    def test_template_instruction_ap_rejected(self):
        tai_ap = (
            "The character's attack power or destructive capacity "
            "(in bold; add any explanations using brackets, not in bold)."
        )
        self.assertIn("template_instruction", boilerplate_reasons(tai_ap, scalar=True))
        self.assertIn("template_instruction", boilerplate_reasons(tai_ap, scalar=False))

    def test_template_tier_and_keys_rejected(self):
        self.assertTrue(boilerplate_reasons("Current Tier of the character (in bold).", scalar=True))
        keys = (
            "For characters who have transformation stages/power-ups or who become "
            "stronger through certain points of the story, insert those "
            "transformations/power-ups"
        )
        self.assertTrue(boilerplate_reasons(keys, scalar=True))

    def test_markup_residue_scalar_rejected(self):
        self.assertIn("markup_residue", boilerplate_reasons("600px|center |-|The Reaper=600px|center", scalar=True))
        self.assertIn("markup_residue", boilerplate_reasons("{{Border|Scroll=No|content= x", scalar=True))

    def test_clean_stat_text_passes(self):
        good = "Small Building level (Smashed a semi-truck with a casual swing, comparable to the Grim Reaper)"
        self.assertEqual(boilerplate_reasons(good, scalar=True), [])
        wall = "Wall level+ (Can damage armored soldiers and crack concrete barriers)"
        self.assertEqual(boilerplate_reasons(wall, scalar=True), [])

    def test_insubstantive_scalar_rejected(self):
        self.assertIn("insubstantive", boilerplate_reasons("Unknown", scalar=True))


if __name__ == "__main__":
    unittest.main()
