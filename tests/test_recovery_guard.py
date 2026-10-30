
"""Unit tests for the Fix A evidence-recovery guard.

Cases are calibrated on the four merges that went wrong in the first
recovery run (Caiman / Yoru / Tai Kamiya / Galatea) plus the fanon-page
shapes that recovered correctly (Korosensei, Shinobu Kocho).
"""

import unittest
from typing import ClassVar

from battlebot.review.auto_repair import (
    _guard_name_match,
    apply_primary_profile_state,
    attempt_field_map,
    attempt_from_result,
    bare_qualifier_reasons,
    boilerplate_reasons,
    clean_item_tails,
    continuity_check,
    editorial_item_reasons,
    eligible_primary_attempts,
    evaluate_recovery_guard,
    filter_list_field_items,
    filter_list_field_items_detailed,
    fragment_item_reasons,
    fragment_scalar_reasons,
    infobox_header_reasons,
    placeholder_item_reasons,
    stat_field_rejection_reasons,
    template_stat_reasons,
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


def promotable_profile(**overrides):
    """A profile satisfying the schema eligibility contract: core stats
    with linked source ids, a usable linked ability, and a mediawiki
    source carrying revision metadata. Frag-11: the promotion branch
    requires this contract, so guard tests for promotion must build
    from here, not from a bare generation dict."""
    prof = {
        "name": "Test Hero",
        "franchise": "Testverse",
        "profile_type": "needs_review",
        "status": "needs_review",
        "battle_eligible": False,
        "power_scale": {
            "attack_potency": {"text": "Building level", "source_ids": ["src1"]},
            "speed": {"text": "Supersonic", "source_ids": ["src1"]},
            "durability": {"text": "Building level", "source_ids": ["src1"]},
        },
        "abilities": [
            {"name": "Flight", "description": "Can fly", "source_ids": ["src1"]}
        ],
        "sources": [
            {
                "id": "src1",
                "source_type": "mediawiki",
                "title": "Test Hero",
                "url": "https://vsbattles.fandom.com/wiki/Test_Hero",
                "revision_id": "123",
                "revision_timestamp": "2026-01-01T00:00:00Z",
            }
        ],
        "generation": {"ineligible_reasons": ["needs_review"], "confidence": 0.6},
        "review": {},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(prof.get(key), dict):
            prof[key] = {**prof[key], **value}
        else:
            prof[key] = value
    return prof


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


class ItemFilterTests(unittest.TestCase):
    """Regression: the first gated sample's Nobara merge.

    Her sole recovered ability was a fanon template placeholder item.
    The section-level filter could not see it; the item filter must
    reject the item, and a field of nothing else recovers nothing.
    """

    NOBARA_PLACEHOLDER = (
        "A list of the character's general abilities "
        "(Please add links to the abilities' pages)"
    )

    def test_nobara_placeholder_item_flagged(self):
        reasons = placeholder_item_reasons(self.NOBARA_PLACEHOLDER)
        self.assertIn("placeholder_instruction", reasons)

    def test_nobara_placeholder_only_field_recovers_nothing(self):
        kept, dropped = filter_list_field_items(self.NOBARA_PLACEHOLDER)
        self.assertEqual(kept, "")
        self.assertEqual(len(dropped), 1)
        self.assertIn("placeholder_instruction", dropped[0]["reasons"])

    def test_mixed_list_keeps_only_substantive_items(self):
        kept, dropped = filter_list_field_items(
            "Cursed Energy Manipulation, Straw Doll Technique, "
            "Please add more abilities here"
        )
        self.assertIn("Cursed Energy Manipulation", kept)
        self.assertIn("Straw Doll Technique", kept)
        self.assertNotIn("Please add", kept)
        self.assertEqual(len(dropped), 1)

    def test_media_fragment_item_dropped(self):
        kept, dropped = filter_list_field_items(
            "Weakness to sunlight, File:Weakness diagram.png, Limited stamina"
        )
        self.assertIn("Weakness to sunlight", kept)
        self.assertIn("Limited stamina", kept)
        self.assertNotIn("File:", kept)
        self.assertTrue(any("media_fragment" in d["reasons"] for d in dropped))

    def test_stat_instruction_item_flagged(self):
        item = (
            "The character's attack power or destructive capacity "
            "(in bold; add any explanations using brackets, not in bold)"
        )
        self.assertIn("template_instruction", placeholder_item_reasons(item))

    def test_real_ability_items_pass(self):
        kept, dropped = filter_list_field_items(
            "Flight, Superhuman Strength, Regeneration, "
            "Straw Doll Technique: Resonance"
        )
        self.assertEqual(dropped, [])
        self.assertIn("Flight", kept)
        self.assertIn("Regeneration", kept)
        self.assertIn("Straw Doll Technique: Resonance", kept)

    def test_empty_field_is_neutral(self):
        self.assertEqual(filter_list_field_items(""), ("", []))
        self.assertEqual(filter_list_field_items(None), ("", []))


class InfoboxHeaderTests(unittest.TestCase):
    """Regression: Kamui and The Captain got their source page's
    infobox header merged as the tier text."""

    KAMUI_TIER = (
        "Name: Kamui | Origin: Gintama | Gender: Male | Age: 18 | "
        "Classification: Yato, Member of the Harusame"
    )

    def test_infobox_header_tier_rejected(self):
        self.assertIn("infobox_header", infobox_header_reasons(self.KAMUI_TIER))

    def test_newline_header_dump_rejected(self):
        dump = "Name: The Captain\nOrigin: Hellsing\nGender: Male\nStatus: Deceased"
        self.assertIn("infobox_header", infobox_header_reasons(dump))

    def test_two_header_keys_not_enough(self):
        self.assertEqual(infobox_header_reasons("Name: Kamui | Origin: Gintama"), [])

    def test_real_stat_text_not_infobox(self):
        good = (
            "Small Town level (Destroyed several buildings and a bridge "
            "in his fight with Sougo), possibly higher"
        )
        self.assertEqual(infobox_header_reasons(good), [])
        self.assertEqual(infobox_header_reasons("Attack Potency: Wall level"), [])
        self.assertEqual(infobox_header_reasons("At least City level, likely far higher"), [])

class Iteration3RegressionTests(unittest.TestCase):
    """Regression: the second gated sample's two escapes.

    Sailor Galaxia's tier was an infobox dump in comma/space shape,
    which the separator-based header check missed. Aladdin's sole
    weakness item was page scaffolding (section markers + the
    victories/losses record headers), which no item pattern matched.
    """

    GALAXIA_TIER = (
        "Key: Sailor Galaxia Name: Galaxia, the Golden Queen of "
        "Shadow Galactica, Origin: Pretty Soldier Sailor Moon "
        "Gender: Female Age: Unknown"
    )
    ALADDIN_SCAFFOLD = "None Notable == Others == Notable Victories: Notable Losses:"

    # -- infobox: separator-agnostic ---------------------------------
    def test_galaxia_comma_shape_header_rejected(self):
        self.assertIn("infobox_header", infobox_header_reasons(self.GALAXIA_TIER))

    def test_space_separated_header_dump_rejected(self):
        dump = "Name: Galaxia Origin: Sailor Moon Gender: Female Age: Ancient"
        self.assertIn("infobox_header", infobox_header_reasons(dump))

    def test_key_prefix_counts_toward_threshold(self):
        # Leading Key: plus two more header keys is a dump...
        dump = "Key: Base Form Name: Galaxia, Origin: Pretty Soldier Sailor Moon"
        self.assertIn("infobox_header", infobox_header_reasons(dump))

    def test_key_prefix_alone_is_not_a_dump(self):
        # ...but a Key: label with no other header keys is not enough.
        text = "Key: At least Planet level (blew up a planet in her base form), likely far higher"
        self.assertEqual(infobox_header_reasons(text), [])

    def test_clean_prose_stat_with_commas_passes(self):
        prose = (
            "At least Multi-City Block level (Traded blows with Eternal "
            "Sailor Moon, shattered her brooch, and forced her to the "
            "brink), possibly far higher"
        )
        self.assertEqual(infobox_header_reasons(prose), [])
        comparable = (
            "Planet level (Comparable to Sailor Moon, who destroyed a "
            "planet-sized dimension, and can harm her directly)"
        )
        self.assertEqual(infobox_header_reasons(comparable), [])

    # -- items: page scaffolding --------------------------------------
    def test_aladdin_scaffolding_item_flagged(self):
        self.assertIn("page_scaffolding", placeholder_item_reasons(self.ALADDIN_SCAFFOLD))

    def test_aladdin_scaffolding_only_field_recovers_nothing(self):
        kept, dropped = filter_list_field_items(self.ALADDIN_SCAFFOLD)
        self.assertEqual(kept, "")
        self.assertEqual(len(dropped), 1)
        self.assertIn("page_scaffolding", dropped[0]["reasons"])

    def test_none_notable_standalone_item_flagged(self):
        self.assertIn("placeholder_instruction", placeholder_item_reasons("None Notable"))
        self.assertIn("placeholder_instruction", placeholder_item_reasons("None notable."))

    def test_section_marker_item_flagged(self):
        item = "== Weaknesses == Limited stamina after prolonged fights"
        self.assertIn("page_scaffolding", placeholder_item_reasons(item))

    def test_notable_record_header_item_flagged(self):
        self.assertIn(
            "page_scaffolding",
            placeholder_item_reasons("Notable Victories: Goku, Vegeta"),
        )

    def test_prose_victories_losses_item_passes(self):
        prose = (
            "Prone to overconfidence after hard-fought victories, and "
            "his losses against faster opponents have exposed his "
            "stamina limits"
        )
        self.assertEqual(placeholder_item_reasons(prose), [])
        kept, dropped = filter_list_field_items("Limited stamina, " + prose)
        self.assertEqual(dropped, [])
        self.assertIn("Limited stamina", kept)
        self.assertIn("stamina limits", kept)

    def test_scaffolding_mixed_with_real_items(self):
        kept, dropped = filter_list_field_items(
            "Weakness to sunlight, " + self.ALADDIN_SCAFFOLD
        )
        self.assertIn("Weakness to sunlight", kept)
        self.assertNotIn("Notable Victories", kept)
        self.assertEqual(len(dropped), 1)


class FragmentScreenTests(unittest.TestCase):
    """Regression: gated sample 50d's five fragment-debris shapes.

    The sample had zero franchise/continuity/infobox failures; it
    failed because the parser's section/list splitting shed fragments
    (Beast Boy / Captain Atom / Big Barda / Circe merges). Each shape
    gets a verbatim regression case plus controls proving legitimate
    content survives the screen.
    """

    BEAST_BOY_BUNDLE = (
        "Resistance to Extreme Temperatures), Berserker Mode, "
        "Fire Manipulation, Regeneration"
    )
    SECTION_BUNDLE = (
        "None Notable Notable Attacks/Techniques: Beast Boy (comics) "
        "Category:STAYDENT Category:Tier 2"
    )

    # -- shape 1: section-boundary / category markup -------------------
    def test_category_markup_item_flagged(self):
        self.assertIn("category_markup", fragment_item_reasons(self.SECTION_BUNDLE))

    def test_section_header_item_flagged(self):
        self.assertIn("section_header", fragment_item_reasons(self.SECTION_BUNDLE))
        self.assertIn(
            "section_header",
            fragment_item_reasons("Notable Attacks/Techniques: Animal Imitation"),
        )
        self.assertIn("section_header", fragment_item_reasons("Weaknesses:"))

    def test_filter_drops_markup_and_header_items(self):
        kept, dropped = filter_list_field_items(
            "Limited stamina, Category:Tier 2, "
            "Notable Attacks/Techniques: Animal Imitation"
        )
        self.assertEqual(kept, "Limited stamina")
        self.assertEqual(len(dropped), 2)
        self.assertTrue(any("category_markup" in d["reasons"] for d in dropped))
        self.assertTrue(any("section_header" in d["reasons"] for d in dropped))

    # -- shape 2: scalar tail-fragments --------------------------------
    def test_scalar_tail_fragment_flagged(self):
        self.assertIn(
            "scalar_tail_fragment", fragment_scalar_reasons(", higher as Werebeast")
        )
        self.assertIn(
            "scalar_tail_fragment",
            fragment_scalar_reasons("higher with the power of the Moon"),
        )

    def test_clean_tier_values_pass_scalar_screen(self):
        self.assertEqual(fragment_scalar_reasons("8-C"), [])
        self.assertEqual(fragment_scalar_reasons("At least 8-C, likely higher"), [])
        # A full value that merely CONTAINS a continuation survives.
        self.assertEqual(
            fragment_scalar_reasons("8-C, higher as Werebeast"), []
        )

    # -- shape 3: sub-2-word weakness shards ---------------------------
    def test_weakness_shards_flagged(self):
        for shard in ("space", "energy"):
            self.assertIn(
                "weakness_fragment",
                fragment_item_reasons(shard, section="weaknesses"),
            )

    def test_filter_drops_weakness_shards_keeps_sentence(self):
        kept, dropped = filter_list_field_items(
            "space, energy, Weakness to sunlight", section="weaknesses"
        )
        self.assertEqual(kept, "Weakness to sunlight")
        self.assertEqual(len(dropped), 2)
        self.assertTrue(all("weakness_fragment" in d["reasons"] for d in dropped))

    def test_single_word_ability_not_size_checked(self):
        self.assertEqual(fragment_item_reasons("Flight"), [])
        self.assertEqual(
            fragment_item_reasons("Flight", section="powers_and_abilities"), []
        )
        kept, dropped = filter_list_field_items(
            "Flight", section="powers_and_abilities"
        )
        self.assertEqual((kept, dropped), ("Flight", []))

    def test_normal_weakness_sentence_passes(self):
        sentence = (
            "Vulnerable to high-frequency sound, which disrupts his "
            "shape-shifting and leaves him disoriented"
        )
        self.assertEqual(fragment_item_reasons(sentence, section="weaknesses"), [])

    # -- shape 4: comma bundle with stray paren -------------------------
    def test_unbalanced_parenthesis_bundle_flagged(self):
        self.assertIn(
            "unbalanced_parenthesis", fragment_item_reasons(self.BEAST_BOY_BUNDLE)
        )

    def test_filter_drops_bundle_keeps_clean_items(self):
        # split_listish holds a "Resistance to..." run together as one
        # piece; the piece must drop whole, neighbours must survive.
        kept, dropped = filter_list_field_items("Flight, " + self.BEAST_BOY_BUNDLE)
        self.assertEqual(kept, "Flight")
        self.assertEqual(len(dropped), 1)
        self.assertIn("unbalanced_parenthesis", dropped[0]["reasons"])

    def test_balanced_parenthesis_ability_passes(self):
        self.assertEqual(fragment_item_reasons("Regeneration (Low-Mid)"), [])
        kept, dropped = filter_list_field_items("Regeneration (Low-Mid), Flight")
        self.assertEqual(dropped, [])
        self.assertIn("Regeneration (Low-Mid)", kept)

    # -- shape 5: conjunction orphans / glued items ---------------------
    def test_conjunction_orphan_leading_flagged(self):
        self.assertIn(
            "conjunction_orphan",
            fragment_item_reasons("and Healing with her Mother Box"),
        )
        self.assertIn(
            "conjunction_orphan",
            fragment_item_reasons("and Astral Projection (shown here)"),
        )

    def test_conjunction_orphan_trailing_flagged(self):
        self.assertIn(
            "conjunction_orphan",
            fragment_item_reasons("Gravity Manipulation with her Mega Rod and"),
        )

    def test_glued_resistance_item_flagged(self):
        self.assertIn(
            "glued_fragment", fragment_item_reasons("Resistance to: Disease Manipulation")
        )
        # The un-glued form is a normal item and passes.
        self.assertEqual(fragment_item_reasons("Resistance to Disease Manipulation"), [])

    def test_long_prose_clause_not_orphaned(self):
        # Comma-splitting a prose weakness legitimately yields a clause
        # starting with "and"; at 11 words it is substance, not a shard.
        clause = (
            "and his losses against faster opponents have exposed his "
            "stamina limits"
        )
        self.assertEqual(fragment_item_reasons(clause, section="weaknesses"), [])

    # -- cross-shape controls -------------------------------------------
    def test_comma_description_ability_passes(self):
        item = "Enhanced senses, including night vision and tracking by scent"
        self.assertEqual(fragment_item_reasons(item), [])

    def test_colon_technique_name_passes(self):
        self.assertEqual(fragment_item_reasons("Straw Doll Technique: Resonance"), [])


class TailCleaningTests(unittest.TestCase):
    """Regression: gated sample 50e's editor-note tails and
    version-key label items. Chris-approved treatment: strip the
    tail off a substantive clause, reject an item that is only the
    note/label."""

    ETRIGAN = (
        "particular high frequencies and Order and Chaos. "
        "Notes: Before making any changes to this page"
    )
    GRODD_NOTE = "Deviantart 2 Note: Before making any changes to this page"
    DEATHSTROKE = (
        "Often lashes out in rage Note: This profile is based on "
        "what is in Death Battles video"
    )
    GRODD_RAGE = (
        "Grodd is prone to blind savage rage when angered. "
        "Respect Threads: Amino Apps"
    )

    # -- shape 6: editor-note tails ------------------------------------
    def test_editor_note_tail_stripped_off_clause(self):
        cleaned, reasons = clean_item_tails(self.ETRIGAN)
        self.assertEqual(
            cleaned, "particular high frequencies and Order and Chaos"
        )
        self.assertEqual(reasons, ["editor_note_tail"])

    def test_editor_note_tail_stripped_without_footer_phrase(self):
        cleaned, reasons = clean_item_tails(self.DEATHSTROKE)
        self.assertEqual(cleaned, "Often lashes out in rage")
        self.assertEqual(reasons, ["editor_note_tail"])

    def test_markerless_footer_tail_stripped(self):
        item = (
            "this profile deals with the Johnny Blaze version of "
            "Ghost Rider in the main 616 Marvel universe. "
            "*Before making any changes to this page"
        )
        cleaned, reasons = clean_item_tails(item)
        self.assertEqual(
            cleaned,
            "this profile deals with the Johnny Blaze version of "
            "Ghost Rider in the main 616 Marvel universe",
        )
        self.assertEqual(reasons, ["editor_note_tail"])

    def test_bare_footer_item_rejected(self):
        cleaned, reasons = clean_item_tails(
            "Before making any changes to this page"
        )
        self.assertEqual(cleaned, "")
        self.assertIn("editor_note_item", reasons)

    def test_placeholder_head_note_item_rejected(self):
        cleaned, reasons = clean_item_tails(
            "None notable Note: Before making any changes to this page"
        )
        self.assertEqual(cleaned, "")
        self.assertIn("editor_note_item", reasons)

    def test_label_head_note_item_rejected_with_both_reasons(self):
        cleaned, reasons = clean_item_tails(self.GRODD_NOTE)
        self.assertEqual(cleaned, "")
        self.assertIn("editor_note_item", reasons)
        self.assertIn("version_key_label", reasons)

    # -- shape 7: version-key labels ------------------------------------
    def test_bare_version_key_label_rejected(self):
        for item in ("Deviantart 1", "Deviantart 2"):
            cleaned, reasons = clean_item_tails(item)
            self.assertEqual(cleaned, "")
            self.assertIn("version_key_label", reasons)

    def test_version_key_label_tail_stripped_off_clause(self):
        cleaned, reasons = clean_item_tails(self.GRODD_RAGE)
        self.assertEqual(
            cleaned, "Grodd is prone to blind savage rage when angered"
        )
        self.assertEqual(reasons, ["version_key_label_tail"])

    def test_amino_leading_ability_not_a_label(self):
        # "Amino" alone is not the label; the observed debris shape
        # is the site label "Amino Apps".
        item = "Amino Acid Manipulation"
        self.assertEqual(clean_item_tails(item), (item, []))

    def test_plain_item_untouched(self):
        item = "Vulnerable to holy weapons"
        self.assertEqual(clean_item_tails(item), (item, []))

    # -- filter integration ----------------------------------------------
    def test_filter_strips_tail_and_records_it(self):
        kept, dropped, stripped = filter_list_field_items_detailed(
            "Vulnerable to holy weapons, " + self.ETRIGAN,
            section="weaknesses",
        )
        self.assertEqual(
            kept,
            "Vulnerable to holy weapons, "
            "particular high frequencies and Order and Chaos",
        )
        self.assertEqual(dropped, [])
        self.assertEqual(len(stripped), 1)
        self.assertIn("editor_note_tail", stripped[0]["reasons"])
        self.assertEqual(
            stripped[0]["kept"],
            "particular high frequencies and Order and Chaos",
        )

    def test_filter_drops_note_only_and_label_items(self):
        kept, dropped, stripped = filter_list_field_items_detailed(
            "Weakness to sunlight, " + self.GRODD_NOTE + ", Deviantart 1",
            section="weaknesses",
        )
        self.assertEqual(kept, "Weakness to sunlight")
        self.assertEqual(stripped, [])
        self.assertEqual(len(dropped), 2)
        all_reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("editor_note_item", all_reasons)
        self.assertIn("version_key_label", all_reasons)


class ProseShardTests(unittest.TestCase):
    """Regression: gated sample 50e's multi-word prose comma-shards
    (doctor-fate-rebirth) plus corpus-calibrated controls. The rule
    is weaknesses-only and conservative: pronoun-led and verb-bearing
    clauses from the live corpus must survive."""

    def test_doctor_fate_shards_flagged(self):
        for shard in ("a woman and a god", "specifically Kent"):
            self.assertIn(
                "prose_shard",
                fragment_item_reasons(shard, section="weaknesses"),
            )

    def test_name_list_appositive_shard_flagged(self):
        self.assertIn(
            "prose_shard",
            fragment_item_reasons(
                "Inza (Kent's wife) and Nabu.", section="weaknesses"
            ),
        )

    def test_such_as_shard_flagged(self):
        self.assertIn(
            "prose_shard",
            fragment_item_reasons("such as poison", section="weaknesses"),
        )

    def test_trailing_colon_header_flagged(self):
        self.assertIn(
            "section_header",
            fragment_item_reasons("The True Fate:", section="weaknesses"),
        )

    def test_prose_shard_not_applied_to_abilities(self):
        self.assertEqual(
            fragment_item_reasons(
                "a woman and a god", section="powers_and_abilities"
            ),
            [],
        )

    def test_filter_drops_shards_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "a woman and a god, specifically Kent, Weakness to sunlight",
            section="weaknesses",
        )
        self.assertEqual(kept, "Weakness to sunlight")
        self.assertEqual(len(dropped), 2)
        self.assertTrue(all("prose_shard" in d["reasons"] for d in dropped))

    # -- corpus controls: real items that must survive -------------------
    def test_corpus_short_weaknesses_pass(self):
        # "rendering them berserk" was in this list before frag-8, but
        # it is a gerund-led fragment of Axl's ability prose ("effects
        # on his opponents, rendering them berserk, paralyzed, blinded
        # ...") misfiled as a weakness -- an offensive effect on
        # others, not a limitation on the owner. The frag-8 shard
        # screen deliberately drops it; it is covered by the shard
        # tests instead.
        for item in (
            "Weak to Dragon",
            "Vulnerable to Dragon",
            "special defense",
            "contains molecular to sub-atomic sensors",
        ):
            self.assertEqual(
                fragment_item_reasons(item, section="weaknesses"),
                [],
                msg=item,
            )

    def test_corpus_clause_weaknesses_pass(self):
        for item in (
            "he can simply use the opponent's abilities",
            "as the Attack Forme lowers durability",
        ):
            self.assertEqual(
                fragment_item_reasons(item, section="weaknesses"),
                [],
                msg=item,
            )


class ProseShardContinuationTests(unittest.TestCase):
    """Regression: gated sample 50h's escapes -- weakness prose shards
    that carry an auxiliary verb or run past the prose-shard word caps
    (raven-rebirth / raven-prime-earth, comma-splits of the Soul Self
    sentence). The extension keys on dangling ends and subjectless
    long continuations; complete clauses WITH auxiliaries survive."""

    def test_raven_aux_verb_shard_flagged(self):
        self.assertIn(
            "prose_shard_continuation",
            fragment_item_reasons("have it carry her", section="weaknesses"),
        )

    def test_raven_long_infinitive_chain_flagged(self):
        self.assertIn(
            "prose_shard_continuation",
            fragment_item_reasons(
                "use it to absorb energy from something or trap someone "
                "in a pocket dimension",
                section="weaknesses",
            ),
        )

    def test_raven_dangling_shard_flagged(self):
        self.assertIn(
            "prose_shard_continuation",
            fragment_item_reasons(
                "Can be sometimes exhausted by using her",
                section="weaknesses",
            ),
        )

    def test_continuation_not_applied_to_abilities(self):
        self.assertEqual(
            fragment_item_reasons(
                "have it carry her", section="powers_and_abilities"
            ),
            [],
        )

    def test_filter_drops_raven_shards_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "have it carry her, Can be sometimes exhausted by using her, "
            "Weakness to sunlight",
            section="weaknesses",
        )
        self.assertEqual(kept, "Weakness to sunlight")
        self.assertEqual(len(dropped), 2)
        self.assertTrue(
            all("prose_shard_continuation" in d["reasons"] for d in dropped)
        )

    # -- controls: complete clauses, auxiliaries included ---------------
    def test_complete_clauses_with_auxiliaries_pass(self):
        for item in (
            "She can be killed by removing her heart",
            ("He has been weakened by the loss of his powers and can no "
            "longer fight at full strength"),
            ("Loses her powers when she is exposed to red sunlight for "
            "too long"),
            "Can be harmed by silver weapons",
        ):
            self.assertEqual(
                fragment_item_reasons(item, section="weaknesses"),
                [],
                msg=item,
            )

    def test_subject_led_long_clauses_pass(self):
        # Corpus-calibration controls: past-tense clauses head with a
        # subject pronoun or a proper noun; the long-continuation rule
        # spares both shapes.
        for item in (
            "he learned how to utilize his curse to his advantage",
            ("which allowed Denji to successfully ambush her in their "
            "final confrontation"),
        ):
            self.assertEqual(
                fragment_item_reasons(item, section="weaknesses"),
                [],
                msg=item,
            )

    def test_headed_clauses_ending_on_pronouns_pass(self):
        # Corpus-calibration controls: whole clauses whose object is
        # a pronoun end on that pronoun legitimately ("...control
        # them", "...with it"); only subjectless dangling ends are
        # shards.
        for item in (
            "Whitesnake can control them",
            "it rips out his heart with it",
            "Gray possesses extreme mastery over it",
            "Using One For All in his weakened state hurts him",
        ):
            self.assertEqual(
                fragment_item_reasons(item, section="weaknesses"),
                [],
                msg=item,
            )


def comic_profile(name, variant_name=None, franchise="DC"):
    prof = profile(name, franchise, "comic")
    if variant_name is not None:
        prof["variant"] = {
            "variant_name": variant_name,
            "variant_type": "version",
            "source_key": "",
            "default_variant": False,
        }
    return prof


class ContinuityGuardTests(unittest.TestCase):
    """Regression: the iteration-3 sample's continuity substitutions.

    Version-scoped profiles took evidence from the right character in
    the right franchise but the WRONG continuity: four Amanda Waller
    comics profiles from the DCAU page, Animal Man (Post-Flashpoint)
    from the Post-Crisis page, Apollo (Post-Crisis) from the
    Post-Flashpoint page, Aquaman from the DCEU film page. Name and
    franchise checks all pass on these pages; only a continuity check
    rejects them.
    """

    DCAU_CATEGORIES: ClassVar[list[str]] = ["DC Animated Universe", "Characters", "Tier 9"]

    def test_waller_post_crisis_rejects_dcau(self):
        result = verdict(
            comic_profile("Amanda Waller (Post-Crisis)", "Post-Crisis"),
            "Amanda Waller (Post-Crisis)",
            "Amanda Waller (DCAU)",
            origin="DC Animated Universe",
            categories=self.DCAU_CATEGORIES,
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(result["name_match"])
        self.assertIn("continuity_mismatch", result["reasons"])
        self.assertEqual(result["continuity"]["page_continuity"], "dcau")
        self.assertEqual(result["continuity"]["profile_scope"], "post-crisis")

    def test_waller_dc_comics_variant_rejects_dcau(self):
        result = verdict(
            comic_profile("Amanda Waller (DC Comics)", "DC Comics"),
            "Amanda Waller (DC Comics)",
            "Amanda Waller (DCAU)",
            origin="DC Animated Universe",
            categories=self.DCAU_CATEGORIES,
        )
        self.assertFalse(result["accepted"])
        self.assertIn("continuity_mismatch", result["reasons"])

    def test_waller_post_flashpoint_rejects_dcau(self):
        result = verdict(
            comic_profile("Amanda Waller (Post-Flashpoint)", "Post-Flashpoint"),
            "Amanda Waller (Post-Flashpoint)",
            "Amanda Waller (DCAU)",
            origin="DC Animated Universe",
            categories=self.DCAU_CATEGORIES,
        )
        self.assertFalse(result["accepted"])
        self.assertIn("continuity_mismatch", result["reasons"])

    def test_waller_base_profile_rejects_dcau(self):
        result = verdict(
            comic_profile("Amanda Waller"),
            "Amanda Waller",
            "Amanda Waller (DCAU)",
            origin="DC Animated Universe",
            categories=self.DCAU_CATEGORIES,
        )
        self.assertFalse(result["accepted"])
        self.assertIn("continuity_mismatch", result["reasons"])

    def test_animal_man_post_flashpoint_rejects_post_crisis_page(self):
        result = verdict(
            comic_profile("Animal Man (Post-Flashpoint)", "Post-Flashpoint"),
            "Animal Man (Post-Flashpoint)",
            "Animal Man (Post-Crisis)",
            origin="DC Comics",
            categories=["DC Comics", "Characters"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("continuity_mismatch", result["reasons"])
        self.assertEqual(result["continuity"]["page_continuity"], "post-crisis")

    def test_apollo_post_crisis_rejects_post_flashpoint_page(self):
        result = verdict(
            comic_profile("Apollo (Post-Crisis)", "Post-Crisis"),
            "Apollo (Post-Crisis)",
            "Apollo (Post-Flashpoint)",
            origin="DC Comics",
            categories=["DC Comics", "Characters"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("continuity_mismatch", result["reasons"])

    def test_aquaman_rejects_dceu_film_page(self):
        result = verdict(
            comic_profile("Aquaman (DC Comics)", "DC Comics"),
            "Aquaman (DC Comics)",
            "Aquaman (DC Extended Universe)",
            origin="DC Extended Universe",
            categories=["DC Extended Universe", "Characters"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("continuity_mismatch", result["reasons"])
        self.assertEqual(result["continuity"]["page_continuity"], "dceu")

    def test_prime_earth_accepts_post_flashpoint_flagship(self):
        # Known equivalence: Prime Earth IS the Post-Flashpoint /
        # New 52 continuity (the iteration-3 audit kept exactly this).
        result = verdict(
            comic_profile("Apollo (Prime Earth)", "Prime Earth"),
            "Apollo (Prime Earth)",
            "Apollo (Post-Flashpoint)",
            origin="DC Comics",
            categories=["DC Comics", "Characters"],
        )
        self.assertTrue(result["accepted"], result["reasons"])
        self.assertNotIn("continuity_mismatch", result["reasons"])

    def test_generic_profile_accepts_print_flagship(self):
        result = verdict(
            comic_profile("Aquaman"),
            "Aquaman",
            "Aquaman (Post-Crisis)",
            origin="DC Comics",
            categories=["DC Comics", "Characters"],
        )
        self.assertTrue(result["accepted"], result["reasons"])

    def test_scoped_profile_accepts_unsignalled_page(self):
        # No positive continuity evidence on the page: no rejection.
        result = verdict(
            comic_profile("Apollo (Post-Crisis)", "Post-Crisis"),
            "Apollo (Post-Crisis)",
            "Apollo",
            origin="DC Comics",
            categories=["DC Comics", "Characters"],
        )
        self.assertNotIn("continuity_mismatch", result["reasons"])

    def test_dcau_profile_rejects_comics_page(self):
        result = verdict(
            comic_profile("Amanda Waller (DCAU)", "DCAU"),
            "Amanda Waller (DCAU)",
            "Amanda Waller (Post-Crisis)",
            origin="DC Comics",
            categories=["DC Comics", "Characters"],
        )
        self.assertFalse(result["accepted"])
        self.assertIn("continuity_mismatch", result["reasons"])

    def test_continuity_check_equivalences_directly(self):
        prof = comic_profile("Animal Man (Post-Flashpoint)", "Post-Flashpoint")
        self.assertFalse(
            continuity_check(prof, page_title="Animal Man (Prime Earth)")["mismatch"]
        )
        self.assertFalse(
            continuity_check(prof, page_title="Animal Man (New 52)")["mismatch"]
        )
        self.assertTrue(
            continuity_check(prof, page_title="Animal Man (Rebirth)")["mismatch"]
        )
        self.assertFalse(
            continuity_check(prof, page_title="Animal Man")["mismatch"]
        )


AQUAMAN_EDITORIAL_INTELLIGENCE = (
    "Above Average Note: Please do not edit this page without permission "
    "from the author, as it is still being worked on. "
    "==Explanations & Related Blog Posts== ==Gallery== ==Others== "
    "Notable Victories:"
)


class ScalarScaffoldingTests(unittest.TestCase):
    """Regression: Aquaman Prime Earth's intelligence merged a fanon
    author's editorial note plus page scaffolding, and his stamina was
    the insubstantive 'Self-explanatory'. Scalar stat values had no
    scaffolding screen."""

    def test_editorial_note_scalar_rejected(self):
        self.assertIn(
            "page_scaffolding",
            boilerplate_reasons(AQUAMAN_EDITORIAL_INTELLIGENCE, scalar=True),
        )
        self.assertTrue(stat_field_rejection_reasons(AQUAMAN_EDITORIAL_INTELLIGENCE))

    def test_section_markers_alone_reject_scalar(self):
        self.assertIn(
            "page_scaffolding",
            boilerplate_reasons("City level ==Gallery== extra", scalar=True),
        )

    def test_self_explanatory_is_insubstantive(self):
        self.assertIn(
            "insubstantive", boilerplate_reasons("Self-explanatory", scalar=True)
        )
        self.assertIn(
            "insubstantive", stat_field_rejection_reasons("Self-explanatory")
        )

    def test_clean_scalars_pass_all_screens(self):
        self.assertEqual(
            stat_field_rejection_reasons(
                "Small Building level (Smashed a semi-truck with a casual swing)"
            ),
            [],
        )
        self.assertEqual(
            stat_field_rejection_reasons(
                "Superhuman (Can regain stamina in sunlight)"
            ),
            [],
        )
        self.assertEqual(
            stat_field_rejection_reasons(
                "Varies, up to Solar System level (Far stronger when "
                "exposed to direct sunlight)"
            ),
            [],
        )


class RepairPathContinuityTests(unittest.TestCase):
    """The continuity check and scalar screen in the MAIN repair path
    (attempt_from_result / eligible_primary_attempts) -- the path that
    re-promoted Apollo (Post-Crisis) from Post-Flashpoint evidence."""

    FIELDS: ClassVar[dict[str, str]] = {
        "attack_potency": "Wall level (Can shatter reinforced concrete with a casual strike)",
        "speed": "Supersonic (Can outpace fighter jets in sustained flight)",
        "durability": "Wall level (Shrugged off anti-tank fire at close range)",
        "powers_and_abilities": "Solar Energy Absorption, Flight, Heat Vision",
        "origin": "DC Comics",
    }

    def _attempt(self, prof, title, fields=None):
        source = {
            "id": "vsbattles-test",
            "title": title,
            "url": "https://vsbattles.fandom.com/wiki/" + title.replace(" ", "_"),
            "provider_id": "vsbattles",
            "authority": "high",
            "promotion_allowed": True,
        }
        metadata = {
            "title": title,
            "url": source["url"],
            "revision_id": "42",
            "fetch_status": "fetched",
            "promotion_allowed": True,
            "authority": "high",
            "provider_id": "vsbattles",
        }
        return attempt_from_result(
            prof, source, dict(fields or self.FIELDS), metadata, ok=True, note="ok"
        )

    def test_repair_attempt_flags_cross_continuity(self):
        prof = comic_profile("Apollo (Post-Crisis)", "Post-Crisis")
        attempt = self._attempt(prof, "Apollo (Post-Flashpoint)")
        self.assertTrue(attempt.identity_match)
        self.assertTrue(attempt.continuity_mismatch)
        self.assertIn("post-flashpoint", attempt.continuity_detail)
        self.assertEqual(eligible_primary_attempts([attempt]), [])

    def test_repair_attempt_accepts_matching_continuity(self):
        prof = comic_profile("Apollo (Post-Crisis)", "Post-Crisis")
        attempt = self._attempt(prof, "Apollo (Post-Crisis)")
        self.assertFalse(attempt.continuity_mismatch)
        self.assertEqual(eligible_primary_attempts([attempt]), [attempt])

    def test_repair_attempt_drops_scaffolded_scalars(self):
        prof = comic_profile("Aquaman (Prime Earth)", "Prime Earth")
        fields = dict(self.FIELDS)
        fields["intelligence"] = AQUAMAN_EDITORIAL_INTELLIGENCE
        fields["stamina"] = "Self-explanatory"
        attempt = self._attempt(prof, "Aquaman (Prime Earth)", fields)
        self.assertNotIn("intelligence", attempt.extracted_fields)
        self.assertNotIn("stamina", attempt.extracted_fields)
        dropped = attempt.metadata.get("dropped_scalar_fields") or {}
        self.assertIn("page_scaffolding", dropped.get("intelligence") or [])
        self.assertIn("insubstantive", dropped.get("stamina") or [])
        self.assertIn("attack_potency", attempt.extracted_fields)


class RepairPathItemScreenTests(unittest.TestCase):
    """The item screens in the MAIN repair path (attempt_from_result).

    The recovery path dropped the editor-note footer bundle, but the
    drain's repair path merged it straight back into etrigan and both
    grodd profiles, because repair attempts never item-filtered their
    list fields. These tests prove the screens now fire at the repair
    choke point, with drops/strips recorded on the attempt metadata.
    """

    FIELDS: ClassVar[dict[str, str]] = {
        "attack_potency": "Wall level (Can shatter reinforced concrete with a casual strike)",
        "speed": "Supersonic (Can outpace fighter jets in sustained flight)",
        "durability": "Wall level (Shrugged off anti-tank fire at close range)",
        "powers_and_abilities": "Solar Energy Absorption, Flight, Heat Vision",
        "weaknesses": "Vulnerable to holy weapons",
        "origin": "DC Comics",
    }

    def _attempt(self, prof, fields=None):
        title = str(prof.get("name") or "Test")
        source = {
            "id": "vsbattles-test",
            "title": title,
            "url": "https://vsbattles.fandom.com/wiki/" + title.replace(" ", "_"),
            "provider_id": "vsbattles",
            "authority": "high",
            "promotion_allowed": True,
        }
        metadata = {
            "title": title,
            "url": source["url"],
            "revision_id": "42",
            "fetch_status": "fetched",
            "promotion_allowed": True,
            "authority": "high",
            "provider_id": "vsbattles",
        }
        return attempt_from_result(
            prof, source, dict(fields or self.FIELDS), metadata, ok=True, note="ok"
        )

    def test_repair_attempt_strips_editor_note_tail(self):
        prof = comic_profile("Etrigan (Post-Crisis)", "Post-Crisis")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = (
            "Vulnerable to holy weapons, particular high frequencies "
            "and Order and Chaos. Notes: Before making any changes "
            "to this page"
        )
        attempt = self._attempt(prof, fields)
        merged = attempt_field_map(attempt)["weaknesses"]
        self.assertNotIn("Before making any changes", merged)
        self.assertIn(
            "particular high frequencies and Order and Chaos", merged
        )
        stripped = (attempt.metadata.get("stripped_items") or {}).get(
            "weaknesses"
        ) or []
        self.assertEqual(len(stripped), 1)
        self.assertIn("editor_note_tail", stripped[0]["reasons"])

    def test_repair_attempt_drops_label_items_keeps_clause(self):
        prof = comic_profile("Gorilla Grodd (Post-Crisis)", "Post-Crisis")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = (
            "Grodd is prone to blind savage rage when angered. "
            "Respect Threads: Amino Apps, Deviantart 1, "
            "Deviantart 2 Note: Before making any changes to this page"
        )
        attempt = self._attempt(prof, fields)
        merged = attempt_field_map(attempt)["weaknesses"]
        self.assertEqual(
            merged, "Grodd is prone to blind savage rage when angered"
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        all_reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("version_key_label", all_reasons)
        self.assertIn("editor_note_item", all_reasons)
        stripped = (attempt.metadata.get("stripped_items") or {}).get(
            "weaknesses"
        ) or []
        self.assertEqual(len(stripped), 1)
        self.assertIn("version_key_label_tail", stripped[0]["reasons"])

    def test_repair_attempt_drops_fragment_bundle_from_abilities(self):
        prof = comic_profile("Beast Boy (Post-Crisis)", "Post-Crisis")
        fields = dict(self.FIELDS)
        fields["powers_and_abilities"] = (
            "Flight, Resistance to Extreme Temperatures), "
            "Berserker Mode, Fire Manipulation, Regeneration"
        )
        attempt = self._attempt(prof, fields)
        self.assertEqual(
            attempt_field_map(attempt)["powers_and_abilities"], "Flight"
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "powers_and_abilities"
        ) or []
        self.assertEqual(len(dropped), 1)
        self.assertIn("unbalanced_parenthesis", dropped[0]["reasons"])

    def test_repair_attempt_field_removed_when_only_debris(self):
        prof = comic_profile("Gorilla Grodd (Post-Crisis)", "Post-Crisis")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = "Deviantart 1"
        attempt = self._attempt(prof, fields)
        self.assertNotIn("weaknesses", attempt.extracted_fields)
        self.assertNotIn("weaknesses", attempt_field_map(attempt))
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        self.assertEqual(len(dropped), 1)
        self.assertIn("version_key_label", dropped[0]["reasons"])

    def test_repair_attempt_clean_lists_untouched(self):
        prof = comic_profile("Apollo (Post-Crisis)", "Post-Crisis")
        attempt = self._attempt(prof)
        self.assertEqual(
            attempt_field_map(attempt)["weaknesses"],
            "Vulnerable to holy weapons",
        )
        self.assertEqual(
            attempt_field_map(attempt)["powers_and_abilities"],
            "Solar Energy Absorption, Flight, Heat Vision",
        )
        self.assertNotIn("dropped_items", attempt.metadata)
        self.assertNotIn("stripped_items", attempt.metadata)


class TemplateScreenTests(unittest.TestCase):
    """CSPW template screens (sample 50f's harley-quinn failure).

    The source page was an unfilled character-stats-profiles
    template: its WIP placeholder and its field definitions merged
    as stats, and its instruction / feats-label furniture merged as
    weaknesses. Verbatim regressions first, then the controls that
    must survive.
    """

    # -- (a) WIP-placeholder stats --

    def test_wip_stat_rejected_verbatim(self):
        value = "Will Finish Upon Return"
        self.assertIn("wip_placeholder_stat", template_stat_reasons(value))
        self.assertIn(
            "wip_placeholder_stat", boilerplate_reasons(value, scalar=True)
        )
        self.assertIn(
            "wip_placeholder_stat", stat_field_rejection_reasons(value)
        )

    def test_wip_family_rejected(self):
        for value in (
            "To be added",
            "Will be added soon",
            "To be finished",
            "Coming soon",
            "Will update later",
        ):
            self.assertIn(
                "wip_placeholder_stat", template_stat_reasons(value), value
            )

    # -- (b) field-definition stats --

    def test_field_definition_stat_rejected_verbatim(self):
        value = "The distance the character's attacks/abilities can cover."
        self.assertIn("field_definition_stat", template_stat_reasons(value))
        self.assertIn(
            "field_definition_stat", boilerplate_reasons(value, scalar=True)
        )
        self.assertIn(
            "field_definition_stat", stat_field_rejection_reasons(value)
        )

    # -- stat controls --

    def test_legit_stats_survive_template_screen(self):
        for value in (
            "8-C",
            "Massively Hypersonic+",
            "Standard melee range",
            ("Several meters with energy blasts (Can snipe targets "
            "from rooftops across the city)"),
            "Building level (Destroyed a warehouse with a single strike)",
            "The character's armor plating shrugs off anti-tank fire",
        ):
            self.assertEqual(template_stat_reasons(value), [], value)

    def test_legit_stat_sentences_survive_full_screen(self):
        for value in (
            "Massively Hypersonic+",
            "Standard melee range",
            ("Several meters with energy blasts (Can snipe targets "
            "from rooftops across the city)"),
            "Building level (Destroyed a warehouse with a single strike)",
            "The character's armor plating shrugs off anti-tank fire",
        ):
            self.assertEqual(stat_field_rejection_reasons(value), [], value)

    # -- (c) template-instruction / feats-label items --

    def test_template_instruction_item_rejected_verbatim(self):
        item = (
            "Self-explanatory Feats: List all of the character's "
            "amazing feats. Strength feats"
        )
        self.assertIn("template_instruction", placeholder_item_reasons(item))

    def test_list_all_instruction_rejected(self):
        self.assertIn(
            "template_instruction",
            placeholder_item_reasons("List all of the character's amazing feats"),
        )
        self.assertIn(
            "template_instruction",
            placeholder_item_reasons("Self-explanatory"),
        )

    def test_bare_feats_labels_rejected(self):
        for item in ("speed feats", "durability feats", "Strength feats"):
            self.assertIn("feats_label", placeholder_item_reasons(item), item)

    def test_feats_labels_filtered_from_weaknesses(self):
        kept, dropped = filter_list_field_items(
            "Vulnerable to magic, speed feats, durability feats",
            section="weaknesses",
        )
        self.assertEqual(kept, "Vulnerable to magic")
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("feats_label", reasons)

    def test_substantive_feats_prose_survives(self):
        item = "Has replicated the feats of strength performed by veteran heroes"
        self.assertEqual(placeholder_item_reasons(item), [])
        kept, dropped = filter_list_field_items(item, section="weaknesses")
        self.assertEqual(kept, item)
        self.assertEqual(dropped, [])


class TemplateRepairPathTests(unittest.TestCase):
    """The CSPW template screens at the repair choke point.

    attempt_from_result screens stats via stat_field_rejection_
    reasons (which now includes the template stat screens) and list
    fields via the item filters, so the drain can no longer merge
    the harley template artifacts either.
    """

    FIELDS: ClassVar[dict[str, str]] = {
        "attack_potency": "Wall level (Can shatter reinforced concrete "
        "with a casual strike)",
        "speed": "Supersonic (Can outpace fighter jets in sustained flight)",
        "durability": "Wall level (Shrugged off anti-tank fire at close range)",
        "range": "Standard melee range",
        "powers_and_abilities": "Solar Energy Absorption, Flight, Heat Vision",
        "weaknesses": "Vulnerable to holy weapons",
        "origin": "DC Comics",
    }

    def _attempt(self, prof, fields=None):
        title = str(prof.get("name") or "Test")
        source = {
            "id": "cspw-test",
            "title": title,
            "url": "https://character-stats-profiles.fandom.com/wiki/"
            + title.replace(" ", "_"),
            "provider_id": "cspw",
            "authority": "high",
            "promotion_allowed": True,
        }
        metadata = {
            "title": title,
            "url": source["url"],
            "revision_id": "42",
            "fetch_status": "fetched",
            "promotion_allowed": True,
            "authority": "high",
            "provider_id": "cspw",
        }
        return attempt_from_result(
            prof, source, dict(fields or self.FIELDS), metadata,
            ok=True, note="ok",
        )

    def test_repair_attempt_drops_template_stats(self):
        prof = comic_profile("Harley Quinn (Post-Flashpoint)", "Post-Flashpoint")
        fields = dict(self.FIELDS)
        fields["attack_potency"] = "Will Finish Upon Return"
        fields["range"] = "The distance the character's attacks/abilities can cover."
        attempt = self._attempt(prof, fields)
        merged = attempt_field_map(attempt)
        self.assertNotIn("attack_potency", merged)
        self.assertNotIn("range", merged)
        dropped = attempt.metadata.get("dropped_scalar_fields") or {}
        self.assertIn("wip_placeholder_stat", dropped.get("attack_potency") or [])
        self.assertIn("field_definition_stat", dropped.get("range") or [])
        # Untouched stats survive alongside the drops.
        self.assertEqual(merged["speed"], self.FIELDS["speed"])

    def test_repair_attempt_drops_template_items(self):
        prof = comic_profile("Harley Quinn (Post-Flashpoint)", "Post-Flashpoint")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = (
            "Vulnerable to magic, speed feats, "
            "Self-explanatory Feats: List all of the character's "
            "amazing feats. Strength feats"
        )
        attempt = self._attempt(prof, fields)
        self.assertEqual(
            attempt_field_map(attempt)["weaknesses"], "Vulnerable to magic"
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("feats_label", reasons)
        self.assertIn("template_instruction", reasons)

    def test_repair_attempt_clean_fields_untouched(self):
        prof = comic_profile("Harley Quinn (Post-Flashpoint)", "Post-Flashpoint")
        attempt = self._attempt(prof)
        merged = attempt_field_map(attempt)
        self.assertEqual(merged["attack_potency"], self.FIELDS["attack_potency"])
        self.assertEqual(merged["range"], self.FIELDS["range"])
        self.assertNotIn("dropped_scalar_fields", attempt.metadata)
        self.assertNotIn("dropped_items", attempt.metadata)


class TabKeyCompositeTests(unittest.TestCase):
    """Glued tab-key composite items (sample 50g's harley merge).

    The CSPW tabber's labels were itemized as one ability: "Base
    Hax Hammer Harleen Hax AoR Harley Hax Death Manipulation". The
    screen keys on the tab category label ("Hax") recurring in the
    item's original case -- calibrated to zero hits across the live
    corpus of 67.5k distinct item names.
    """

    COMPOSITE = "Base Hax Hammer Harleen Hax AoR Harley Hax Death Manipulation"

    def test_composite_rejected_verbatim(self):
        self.assertIn(
            "tab_key_composite",
            fragment_item_reasons(self.COMPOSITE, section="powers_and_abilities"),
        )

    def test_composite_filtered_from_mixed_list(self):
        kept, dropped = filter_list_field_items(
            f"Flight, {self.COMPOSITE}, Heat Vision",
            section="powers_and_abilities",
        )
        self.assertEqual(kept, "Flight, Heat Vision")
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("tab_key_composite", reasons)

    def test_legit_ability_names_survive(self):
        for item in (
            "Death Manipulation",
            "Weather Manipulation",
            "Master Swordsmanship",
            "Regeneration (Low-Mid)",
            "Flight (Via Wings)",
            "Death Manipulation (Post-Flashpoint)",
            "Mind Hax",
            "Hax",
            "Soul Physiology & Hollow Physiology (Soul: High-Tier Arrancar)",
            "Explosion Manipulation (Via Burst Bomb, Ink Bomb, Splat Bomb)",
        ):
            self.assertEqual(
                fragment_item_reasons(item, section="powers_and_abilities"),
                [],
                item,
            )
            self.assertEqual(placeholder_item_reasons(item), [], item)


class BareQualifierTests(unittest.TestCase):
    """Bare-qualifier scalars (sample 50g's midnighter merges).

    Tier read "At least" -- the qualifier half of a real value with
    the value token dropped. A value token anywhere makes it real.
    """

    def test_bare_qualifier_rejected_verbatim(self):
        value = "At least"
        self.assertIn("bare_qualifier", bare_qualifier_reasons(value))
        self.assertIn("bare_qualifier", fragment_scalar_reasons(value))
        self.assertIn(
            "bare_qualifier", boilerplate_reasons(value, scalar=True)
        )
        self.assertIn(
            "bare_qualifier", stat_field_rejection_reasons(value)
        )

    def test_qualifier_family_rejected(self):
        for value in ("At most", "Around", "Over", "Likely", "Likely higher"):
            self.assertIn("bare_qualifier", bare_qualifier_reasons(value), value)
            self.assertIn(
                "bare_qualifier", stat_field_rejection_reasons(value), value
            )

    def test_qualified_real_values_survive(self):
        for value in (
            ("At least Small Building level (Destroyed a warehouse "
            "with a single strike)"),
            "At least 8-C, likely higher",
            "8-C",
            "Massively Hypersonic+",
            "Standard melee range",
        ):
            self.assertEqual(bare_qualifier_reasons(value), [], value)
        # Full-screen controls exclude bare "8-C": the pre-existing
        # insubstantive check has always required fuller tier text
        # at the repair choke point.
        for value in (
            ("At least Small Building level (Destroyed a warehouse "
            "with a single strike)"),
            "At least 8-C, likely higher",
            "Massively Hypersonic+",
            "Standard melee range",
        ):
            self.assertEqual(stat_field_rejection_reasons(value), [], value)


class FourthGenRepairPathTests(unittest.TestCase):
    """Both fourth-generation screens at the repair choke point."""

    FIELDS: ClassVar[dict[str, str]] = {
        "tier": "Building level (8-C)",
        "attack_potency": "Wall level (Can shatter reinforced concrete "
        "with a casual strike)",
        "speed": "Supersonic (Can outpace fighter jets in sustained flight)",
        "durability": "Wall level (Shrugged off anti-tank fire at close range)",
        "range": "Standard melee range",
        "powers_and_abilities": "Solar Energy Absorption, Flight, Heat Vision",
        "weaknesses": "Vulnerable to holy weapons",
        "origin": "DC Comics",
    }

    def _attempt(self, prof, fields=None):
        title = str(prof.get("name") or "Test")
        source = {
            "id": "cspw-test",
            "title": title,
            "url": "https://character-stats-profiles.fandom.com/wiki/"
            + title.replace(" ", "_"),
            "provider_id": "cspw",
            "authority": "high",
            "promotion_allowed": True,
        }
        metadata = {
            "title": title,
            "url": source["url"],
            "revision_id": "42",
            "fetch_status": "fetched",
            "promotion_allowed": True,
            "authority": "high",
            "provider_id": "cspw",
        }
        return attempt_from_result(
            prof, source, dict(fields or self.FIELDS), metadata,
            ok=True, note="ok",
        )

    def test_repair_attempt_drops_bare_qualifier_tier(self):
        prof = comic_profile("Midnighter (Post-Crisis)", "Post-Crisis")
        fields = dict(self.FIELDS)
        fields["tier"] = "At least"
        attempt = self._attempt(prof, fields)
        merged = attempt_field_map(attempt)
        self.assertNotIn("tier", merged)
        dropped = attempt.metadata.get("dropped_scalar_fields") or {}
        self.assertIn("bare_qualifier", dropped.get("tier") or [])
        self.assertEqual(merged["speed"], self.FIELDS["speed"])

    def test_repair_attempt_drops_tab_key_composite(self):
        prof = comic_profile("Harley Quinn (Post-Flashpoint)", "Post-Flashpoint")
        fields = dict(self.FIELDS)
        fields["powers_and_abilities"] = (
            "Flight, Base Hax Hammer Harleen Hax AoR Harley Hax "
            "Death Manipulation, Heat Vision"
        )
        attempt = self._attempt(prof, fields)
        self.assertEqual(
            attempt_field_map(attempt)["powers_and_abilities"],
            "Flight, Heat Vision",
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "powers_and_abilities"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("tab_key_composite", reasons)

    def test_repair_attempt_clean_fields_untouched(self):
        prof = comic_profile("Midnighter (Post-Crisis)", "Post-Crisis")
        attempt = self._attempt(prof)
        merged = attempt_field_map(attempt)
        self.assertEqual(merged["tier"], self.FIELDS["tier"])
        self.assertNotIn("dropped_scalar_fields", attempt.metadata)
        self.assertNotIn("dropped_items", attempt.metadata)


class EditorialEssayTests(unittest.TestCase):
    """Sixth generation, family 1: editorial/explanatory essay prose
    merged as items (superman-prime-earth sample 50i -- the profile's
    ENTIRE weaknesses recovery was page essay). Calibrated over the
    stored corpus (196k item texts): 18 raw hits, 4 distinct texts,
    all debris -- the two verbatim families plus an editor
    instruction in hawke. Round 1's generic second-person patterns
    caught descriptive requirement prose ("which you need to have a
    strong body...") and quoted dialogue; the adopted patterns key
    on instructions about the page/text itself."""

    def test_verbatim_essay_fragment_flagged(self):
        self.assertIn(
            "editorial_essay",
            placeholder_item_reasons(
                "as well as how the powers and nature of the character "
                "fundamentally work. This is particularly useful for "
                "more high-tiered characters"
            ),
        )

    def test_verbatim_editor_instruction_flagged(self):
        self.assertIn(
            "editor_instruction",
            placeholder_item_reasons(
                "it is very important that you make sure that the text "
                "has good grammar/sentence structure"
            ),
        )

    def test_specify_instruction_flagged(self):
        self.assertIn(
            "editor_instruction",
            editorial_item_reasons(
                "so you should specify what gender and class type "
                "Hawke is on vs matches"
            ),
        )

    def test_filter_drops_essay_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "it is very important that you make sure that the text has "
            "good grammar/sentence structure, Weakness to sunlight",
            section="weaknesses",
        )
        self.assertEqual(kept, "Weakness to sunlight")
        self.assertEqual(len(dropped), 1)
        self.assertIn("editor_instruction", dropped[0]["reasons"])

    # -- corpus controls: legit content that must survive -------------
    def test_descriptive_requirement_prose_passes(self):
        self.assertEqual(
            editorial_item_reasons(
                "Supernatural Willpower (Was capable of succeeding in "
                "the heaven ascension ritual, which you need to have a "
                "strong body and mind to be able to become an angel "
                "without becoming a mindless beast)"
            ),
            [],
        )

    def test_makes_sure_third_person_passes(self):
        for item in (
            "His suit makes sure the wearer survives vacuum",
            "Makes sure his allies are safe before engaging",
        ):
            self.assertEqual(editorial_item_reasons(item), [], item)

    def test_character_prose_passes(self):
        for item in (
            ("Salem was cursed with immortality by the God of Light, "
            "ensuring she is unable to die so long as Remnant exists"),
            "Weak to Dragon",
            "Flight",
        ):
            self.assertEqual(editorial_item_reasons(item), [], item)


class TechniqueInWeaknessesTests(unittest.TestCase):
    """Sixth generation, family 2: the character's OWN notable
    attacks itemized into weaknesses (starfire sample 50i). The
    content is real; the defect is the section. Calibrated over
    83,206 stored weakness texts: the sampled hits are the defect
    class itself (stored weaknesses fields are heavily polluted
    with misfiled technique lists). Calibration caught one real
    false-positive mechanism -- "blasts" is a noun as often as a
    verb ("She is not immune to her own blasts") -- so the finite
    verb set carries no noun-ambiguous forms."""

    def test_starbolt_verbatim_flagged(self):
        self.assertIn(
            "technique_in_weaknesses",
            fragment_item_reasons(
                "Starbolt: Starfire can fire bolts of stellar energy "
                "out of her hands",
                section="weaknesses",
            ),
        )

    def test_nova_verbatim_flagged(self):
        self.assertIn(
            "technique_in_weaknesses",
            fragment_item_reasons(
                "Nova: Starfire releases an omnidirectional energy pulse",
                section="weaknesses",
            ),
        )

    def test_unlabelled_technique_flagged(self):
        self.assertIn(
            "technique_in_weaknesses",
            fragment_item_reasons(
                "Babylon Guardian fires a blast of energy down the track",
                section="weaknesses",
            ),
        )

    def test_technique_not_applied_to_abilities(self):
        self.assertNotIn(
            "technique_in_weaknesses",
            fragment_item_reasons(
                "Starbolt: Starfire can fire bolts of stellar energy "
                "out of her hands",
                section="powers_and_abilities",
            ),
        )

    def test_filter_drops_techniques_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "Starbolt: Starfire can fire bolts of stellar energy out "
            "of her hands, Nova: Starfire releases an omnidirectional "
            "energy pulse, Weakness to sunlight",
            section="weaknesses",
        )
        self.assertEqual(kept, "Weakness to sunlight")
        self.assertEqual(len(dropped), 2)
        self.assertTrue(
            all("technique_in_weaknesses" in d["reasons"] for d in dropped)
        )

    # -- controls: genuine weaknesses that must survive ---------------
    def test_own_blasts_immunity_weakness_passes(self):
        self.assertNotIn(
            "technique_in_weaknesses",
            fragment_item_reasons(
                "She is not immune to her own blasts", section="weaknesses"
            ),
        )

    def test_draining_technique_weakness_passes(self):
        self.assertNotIn(
            "technique_in_weaknesses",
            fragment_item_reasons(
                "Starbolts: Drawing on stellar energy drains her "
                "reserves over time",
                section="weaknesses",
            ),
        )

    def test_named_vulnerability_passes(self):
        self.assertNotIn(
            "technique_in_weaknesses",
            fragment_item_reasons(
                "Kryptonite: A radioactive mineral that weakens him "
                "and drains his strength",
                section="weaknesses",
            ),
        )

    def test_bare_attack_noun_phrases_pass(self):
        for item in ("energy blasts", "Cyclops's optical blasts"):
            self.assertNotIn(
                "technique_in_weaknesses",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )


class ConcessiveShardTests(unittest.TestCase):
    """Sixth generation, family 3: concessive tail shards
    (starfire sample 50i: "though this is draining to use").
    Calibration round 1 fired on 348 stored weakness texts -- the
    corpus legitimately stores concessive QUALIFIERS as items when
    they carry a real subject and concrete limitation content. The
    adopted rule is the narrow residue: short, demonstrative- or
    subject-less, no concrete content marker, no following main
    clause. Final calibration: 48 raw / 18 distinct, every distinct
    hit a fragment or sentence tail."""

    def test_verbatim_shard_flagged(self):
        self.assertIn(
            "concessive_shard",
            fragment_item_reasons(
                "though this is draining to use", section="weaknesses"
            ),
        )

    def test_calibration_shards_flagged(self):
        for shard in (
            "though in the anime",
            "although people with",
            "though stronger than he ever let Vergil see",
            "though this is usually undesirable",
        ):
            self.assertIn(
                "concessive_shard",
                fragment_item_reasons(shard, section="weaknesses"),
                shard,
            )

    def test_concessive_not_applied_to_abilities(self):
        self.assertNotIn(
            "concessive_shard",
            fragment_item_reasons(
                "though this is draining to use",
                section="powers_and_abilities",
            ),
        )

    def test_filter_drops_shard_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "though this is draining to use, Weakness to sunlight",
            section="weaknesses",
        )
        self.assertEqual(kept, "Weakness to sunlight")
        self.assertEqual(len(dropped), 1)
        self.assertIn("concessive_shard", dropped[0]["reasons"])

    # -- controls: concessive content that must survive ---------------
    def test_main_clause_pairs_pass(self):
        for item in (
            "Though weak to fire, he is resistant to ice",
            "Although she is powerful, her stamina is limited",
            "Though draining, she can use it repeatedly",
            "He is strong, though he tires quickly",
        ):
            self.assertNotIn(
                "concessive_shard",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    def test_content_bearing_qualifiers_pass(self):
        for item in (
            "although this drains her spiritual energy quickly",
            ("though his transformations fix his eyesight for as long "
            "as he uses them"),
            "Although unharmed by virtually any form of damage",
            "although weaker without her helmet",
            "though rage can override these",
            "although this can be circumvented with the Bottomless Gloves",
        ):
            self.assertNotIn(
                "concessive_shard",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )


class SixthGenRepairPathTests(unittest.TestCase):
    """The sixth-generation item screens at the repair choke point."""

    FIELDS: ClassVar[dict[str, str]] = {
        "tier": "Building level (8-C)",
        "attack_potency": "Wall level (Can shatter reinforced concrete "
        "with a casual strike)",
        "speed": "Supersonic (Can outpace fighter jets in sustained flight)",
        "durability": "Wall level (Shrugged off anti-tank fire at close range)",
        "range": "Standard melee range",
        "powers_and_abilities": "Solar Energy Absorption, Flight, Heat Vision",
        "weaknesses": "Vulnerable to holy weapons",
        "origin": "DC Comics",
    }

    def _attempt(self, prof, fields=None):
        title = str(prof.get("name") or "Test")
        source = {
            "id": "cspw-test",
            "title": title,
            "url": "https://character-stats-profiles.fandom.com/wiki/"
            + title.replace(" ", "_"),
            "provider_id": "cspw",
            "authority": "high",
            "promotion_allowed": True,
        }
        metadata = {
            "title": title,
            "url": source["url"],
            "revision_id": "42",
            "fetch_status": "fetched",
            "promotion_allowed": True,
            "authority": "high",
            "provider_id": "cspw",
        }
        return attempt_from_result(
            prof, source, dict(fields or self.FIELDS), metadata,
            ok=True, note="ok",
        )

    def test_repair_attempt_drops_technique_and_shard_from_weaknesses(self):
        prof = comic_profile("Starfire (Post-Flashpoint)", "Post-Flashpoint")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = (
            "Starbolt: Starfire can fire bolts of stellar energy out "
            "of her hands, though this is draining to use, "
            "Vulnerable to holy weapons"
        )
        attempt = self._attempt(prof, fields)
        self.assertEqual(
            attempt_field_map(attempt)["weaknesses"],
            "Vulnerable to holy weapons",
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("technique_in_weaknesses", reasons)
        self.assertIn("concessive_shard", reasons)


class SeventhGenExplicitNoneTests(unittest.TestCase):
    """Frag-7 root cause: an explicit-none weakness section yields ZERO
    weakness items (gate 50j -- The Immortal)."""

    VERBATIM_GATE_VALUE = (
        "None notable Notable Attacks/Techniques: * Out Orbital Punch "
        "* Air Strike ==Notable Matchups== Victories: Losses: "
        "Inconclusive: Category:Characters Category:Wrestlers"
    )

    def test_none_statements_are_placeholder_items(self):
        for text in (
            "None",
            "None notable",
            "None notable.",
            "None known",
            "N/A",
            "No weaknesses",
            "None notable as of Season 2",
            "None Notable (Has never displayed a weakness)",
            "''' None notable",
        ):
            self.assertIn(
                "explicit_none", placeholder_item_reasons(text), text
            )

    def test_none_field_filters_to_empty(self):
        kept, dropped = filter_list_field_items(
            "None notable", section="weaknesses"
        )
        self.assertEqual(kept, "")
        self.assertTrue(dropped)

    def test_verbatim_gate_value_filters_to_empty(self):
        kept, _dropped = filter_list_field_items(
            self.VERBATIM_GATE_VALUE, section="weaknesses"
        )
        self.assertEqual(kept, "")

    def test_mixed_list_keeps_real_weakness_drops_none_piece(self):
        kept, _dropped = filter_list_field_items(
            "Weakness to sunlight, None known", section="weaknesses"
        )
        self.assertEqual(kept, "Weakness to sunlight")

    def test_substantive_sentence_is_not_explicit_none(self):
        text = (
            "No weaknesses known to his enemies, but sunlight kills him"
        )
        self.assertNotIn("explicit_none", placeholder_item_reasons(text))

    def test_no_weakness_to_x_survives_filter(self):
        kept, _dropped = filter_list_field_items(
            "No weakness to magic", section="weaknesses"
        )
        self.assertEqual(kept, "No weakness to magic")


class SeventhGenNameOnlyTechniqueTests(unittest.TestCase):
    """Frag-7 section integrity: a bare technique NAME is not a
    weakness (gate 50j's surviving shape)."""

    def test_verbatim_gate_items_flagged(self):
        for text in ("Out Orbital Punch", "Air Strike"):
            self.assertIn(
                "name_only_technique_in_weaknesses",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_corpus_calibration_examples_flagged(self):
        for text in (
            "Nova Strike",
            "Bullet Punch",
            "Mega Kick",
            "Red Sword Slash",
        ):
            self.assertIn(
                "name_only_technique_in_weaknesses",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_filter_drops_names_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "Out Orbital Punch, Air Strike, Weakness to sunlight",
            section="weaknesses",
        )
        self.assertEqual(kept, "Weakness to sunlight")
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("name_only_technique_in_weaknesses", reasons)

    def test_screen_is_weaknesses_only(self):
        self.assertNotIn(
            "name_only_technique_in_weaknesses",
            fragment_item_reasons(
                "Out Orbital Punch", section="powers_and_abilities"
            ),
        )

    def test_legit_bare_names_survive_as_controls(self):
        # Weapon-noun names: conventionally "can be killed by it".
        # Lowercase/possessive phrases: not name forms (frag-6
        # controls). Limitation semantics: never name-only debris.
        for text in (
            "Archangel Blades",
            "Spirit Bomb",
            "Break Cannon",
            "energy blasts",
            "Cyclops's optical blasts",
            "Weakness to sunlight",
            "Vulnerable to holy weapons",
        ):
            self.assertNotIn(
                "name_only_technique_in_weaknesses",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )


class SeventhGenRepairPathTests(unittest.TestCase):
    """The seventh-generation screens at the repair choke point."""

    FIELDS = SixthGenRepairPathTests.FIELDS

    def _attempt(self, prof, fields=None):
        return SixthGenRepairPathTests()._attempt(prof, fields)

    def test_repair_attempt_drops_name_only_technique(self):
        prof = comic_profile("The Immortal", "Image Comics")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = (
            "Out Orbital Punch, Vulnerable to holy weapons"
        )
        attempt = self._attempt(prof, fields)
        self.assertEqual(
            attempt_field_map(attempt)["weaknesses"],
            "Vulnerable to holy weapons",
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("name_only_technique_in_weaknesses", reasons)

    def test_repair_attempt_drops_explicit_none(self):
        prof = comic_profile("The Immortal", "Image Comics")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = "None notable"
        attempt = self._attempt(prof, fields)
        self.assertNotIn("weaknesses", attempt_field_map(attempt))
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("explicit_none", reasons)

    def test_repair_attempt_drops_markup_residue_none(self):
        # Verbatim from the frag-7 deploy dry-run: the source's
        # section-scoped value carries wikitext bold residue.
        prof = comic_profile("The Immortal", "Image Comics")
        fields = dict(self.FIELDS)
        fields["weaknesses"] = "''' None notable"
        attempt = self._attempt(prof, fields)
        self.assertNotIn("weaknesses", attempt_field_map(attempt))
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("explicit_none", reasons)


class EighthGenFrag8Tests(unittest.TestCase):
    """Frag-8: page disclaimers + prose-sentence shards (gate 50k)."""

    DISCLAIMER_FULL = (
        "any information displayed on any profile based on Death Battle "
        "are solely based on whatever is said in their videos and not my "
        "own opinion. So if a character is weaker or stronger on a "
        "profile than they actually are then it isn't my fault."
    )
    DISCLAIMER_CAPPED = (
        "any information displayed on any profile based on Death Battle "
        "are solely based on whatever is said in their videos and "
    )
    DISCORD_NOTE = (
        "Fought Bhunivelze and ultimately proved to be superior to him "
        "Note: Message me on Discord in case you want to discuss "
        "anything regarding this page (Vanta #2717)"
    )
    SHOVEL_NOTE = (
        "I just inputted everything according to the legends."
    )

    def test_verbatim_disclaimer_flagged(self):
        for text in (self.DISCLAIMER_FULL, self.DISCLAIMER_CAPPED):
            self.assertIn(
                "page_disclaimer",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_disclaimer_editor_notes_flagged(self):
        for text in (self.DISCORD_NOTE, self.SHOVEL_NOTE):
            self.assertIn(
                "page_disclaimer",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_disclaimer_controls_survive(self):
        # "was stated" must not match "as stated" (substring artifact);
        # the trailing lowercase "i" is the 120-char cap cutting a
        # word ("...his death i"), not a pronoun; "My Hero Academia"
        # supplies a phantom "my"; "solely based on" with no
        # first-person voice is a dependency statement, not a
        # disclaimer.
        for text in (
            ("The Post-Flashpoint emanation of Darkseid was stated to be "
            "a fragment of Godhead Darkseid that resulted from his death i"),
            ("requiring a certain amount of consumption of food based on "
            "how she'll use it.My Hero Academia Volume 9 Chapter 72"),
            "His power is solely based on his ring",
            ("According to Morgana, the entire world is a product of "
            "Cognition"),
        ):
            self.assertNotIn(
                "page_disclaimer",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_disclaimer_is_weaknesses_only(self):
        self.assertNotIn(
            "page_disclaimer",
            fragment_item_reasons(
                self.DISCLAIMER_FULL, section="powers_and_abilities"
            ),
        )

    def test_verbatim_shards_flagged(self):
        for text in (
            "but will not meet his desires in many situations. For example",
            "during his fight with the Hulk",
            "rather than supplying a combat-related power.",
            "leading to mistakes.",
        ):
            self.assertIn(
                "prose_sentence_shard",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_lead_clause_not_caught(self):
        # Documented by design: the darwin lead clause is a complete
        # clause, and the item-level rule for it has a 12,691-item
        # false-positive pool (calibration). The gate decides whether
        # it re-merges.
        self.assertNotIn(
            "prose_sentence_shard",
            fragment_item_reasons(
                "His body will adapt to whatever means to make Darwin "
                "survive",
                section="weaknesses",
            ),
        )

    def test_shard_controls_survive(self):
        # Complete clauses (subject-led, contraction-expanded, -ed /
        # irregular past), comma-fronted phrases, limitation markers,
        # and "without" + a noun phrase (a conditional weakness).
        for text in (
            ("however this can be negated by just using an even bigger "
            "shield."),
            "but he cannot fly without his cape",
            "Using his powers drains him quickly",
            "Without his armor",
            "leaving him vulnerable to attack",
            "Being powerless without his ring",
            "Is weak to fire",
            "Lacking in battle experience on his own",
            "suffering from paranoia and extreme anger",
            "leaving it vulnerable after its use",
            ("leaving him incapable of moving without causing himself "
            "further pain"),
            ("increasing their strength and agility at the cost of their "
            "rational thinking"),
            "though he eventually recovered",
            "though he won't die because he's half-human",
            "but they'll even break on contact",
            ("meaning he'll occasionally slide along the ground for a "
            "second"),
            "During full moons, he loses control",
            "With his sword he cuts through anything",
            ("His belief in his superior hunting abilities may cause him "
            "to underestimate opponents"),
        ):
            self.assertNotIn(
                "prose_sentence_shard",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_shard_is_weaknesses_only(self):
        self.assertNotIn(
            "prose_sentence_shard",
            fragment_item_reasons(
                "during his fight with the Hulk",
                section="powers_and_abilities",
            ),
        )

    def test_filter_drops_shards_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "but will not meet his desires in many situations. "
            "For example, during his fight with the Hulk, rather than "
            "supplying a combat-related power., leading to mistakes., "
            "Is weak to fire, Without his armor",
            section="weaknesses",
        )
        self.assertEqual(kept, "Is weak to fire, Without his armor")
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("prose_sentence_shard", reasons)

    def test_repair_attempt_drops_disclaimer_and_shards(self):
        prof = comic_profile("Darwin", "Marvel Comics")
        fields = dict(SixthGenRepairPathTests.FIELDS)
        fields["weaknesses"] = (
            self.DISCLAIMER_FULL + ", but will not meet his desires in "
            "many situations. For example, during his fight with the "
            "Hulk, Is weak to fire"
        )
        attempt = SixthGenRepairPathTests()._attempt(prof, fields)
        self.assertEqual(
            attempt_field_map(attempt)["weaknesses"], "Is weak to fire"
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("page_disclaimer", reasons)
        self.assertIn("prose_sentence_shard", reasons)


class NinthGenFrag9Tests(unittest.TestCase):
    """Frag-9: relative-pronoun openers + or/even/like leading markers
    + numeric-split fragments + header + cut-off clauses (gate 50l,
    venom-earth-616 + venom-marvel-cinematic-universe)."""

    def test_verbatim_relative_pronouns_flagged(self):
        for text in (
            "which has causes drastic shifts in his personality.",
            "which can weaken or nullify the suit's healing powers.",
        ):
            self.assertIn(
                "relative_pronoun_opener",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_relative_pronoun_controls_survive(self):
        # A relative clause WITH a main clause of its own (after a
        # comma, or after a sentence boundary) is a whole item. So is
        # a past-tense relative clause narrating a completed event:
        # the frag-5 long-clause calibration pins "which allowed
        # Denji..." as a zero-reason control, and the screen respects
        # it -- only present-tense/modal property continuations fire.
        for text in (
            "which he fears, so he avoids it",
            "which broke his arm. He never recovered.",
            "that he cannot control, and it burns him",
            ("which allowed Denji to successfully ambush her in their "
            "final confrontation"),
        ):
            self.assertNotIn(
                "relative_pronoun_opener",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_relative_pronoun_is_weaknesses_only(self):
        self.assertNotIn(
            "relative_pronoun_opener",
            fragment_item_reasons(
                "which can weaken or nullify the suit's healing powers.",
                section="powers_and_abilities",
            ),
        )

    def test_verbatim_or_even_like_flagged(self):
        for text in (
            ("or by anything that can pass through the symbiote in "
            "large amounts of energy."),
            "even in the eminence of a battle.",
            "like all others of its kind",
        ):
            self.assertIn(
                "prose_sentence_shard",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_or_even_like_controls_survive(self):
        # "or" + a headed clause, "even without" + a noun phrase (a
        # conditional weakness, mirroring the "without" spare), and a
        # "like" simile with a main clause after a comma.
        for text in (
            "or he can fly",
            "even without her horn",
            "like a human, he needs sleep",
        ):
            self.assertNotIn(
                "prose_sentence_shard",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_verbatim_numeric_split_flagged(self):
        self.assertIn(
            "numeric_split_fragment",
            fragment_item_reasons("000 hertz", section="weaknesses"),
        )

    def test_numeric_controls_survive(self):
        # The limitation spare protects real numeric limits ("180
        # degree blind spot"); one- and two-digit openers never fire.
        for text in (
            "180 degree blind spot",
            "up to 1000 degrees",
            "4 minutes",
        ):
            self.assertNotIn(
                "numeric_split_fragment",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_verbatim_header_cutoff_flagged(self):
        for text in (
            "Sonic and Heat: The Venom symbiote",
            "Darkforce: As Anti-Venom is formed from the Lightforce",
            "Antibody Overuse: If Anti-Venom overuses his healing powers",
        ):
            self.assertIn(
                "header_cutoff",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_header_controls_survive(self):
        # Whole post-colon text: subject-led clause, main clause
        # after a comma, leading finite verb, and a longer definition
        # (the 2-4 word definite-NP bound spares 6-word definitions).
        for text in (
            "Fire: it burns him",
            "Fire: When exposed, he weakens",
            "Sonic: Burns on contact",
            "Flight: The ability to fly with his wings.",
            "Ki Blast: The most basic form of energy wave.",
            "Kryptonite: The green mineral from his homeworld",
        ):
            self.assertNotIn(
                "header_cutoff",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_header_is_weaknesses_only(self):
        self.assertNotIn(
            "header_cutoff",
            fragment_item_reasons(
                "Sonic and Heat: The Venom symbiote",
                section="powers_and_abilities",
            ),
        )

    def test_filter_drops_frag9_debris_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "which has causes drastic shifts in his personality., "
            "which can weaken or nullify the suit's healing powers., "
            "Sonic and Heat: The Venom symbiote, "
            "Darkforce: As Anti-Venom is formed from the Lightforce, "
            "Antibody Overuse: If Anti-Venom overuses his healing "
            "powers, like all others of its kind, radiation up to "
            "4,000 hertz, 000 hertz, or by anything that can pass "
            "through the symbiote in large amounts of energy., even "
            "in the eminence of a battle., Is weak to fire",
            section="weaknesses",
        )
        self.assertEqual(
            kept, "radiation up to 4,000 hertz, Is weak to fire"
        )
        reasons = [r for d in dropped for r in d["reasons"]]
        for reason in (
            "relative_pronoun_opener",
            "header_cutoff",
            "numeric_split_fragment",
            "prose_sentence_shard",
        ):
            self.assertIn(reason, reasons)

    def test_repair_attempt_drops_frag9_debris(self):
        prof = comic_profile("Venom", "Marvel Comics")
        fields = dict(SixthGenRepairPathTests.FIELDS)
        fields["weaknesses"] = (
            "which has causes drastic shifts in his personality., "
            "Sonic and Heat: The Venom symbiote, radiation up to "
            "4,000 hertz, 000 hertz, or by anything that can pass "
            "through the symbiote in large amounts of energy., "
            "Is weak to fire"
        )
        attempt = SixthGenRepairPathTests()._attempt(prof, fields)
        self.assertEqual(
            attempt_field_map(attempt)["weaknesses"],
            "radiation up to 4,000 hertz, Is weak to fire",
        )
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        for reason in (
            "relative_pronoun_opener",
            "header_cutoff",
            "numeric_split_fragment",
            "prose_sentence_shard",
        ):
            self.assertIn(reason, reasons)


class TenthGenFrag10Tests(unittest.TestCase):
    """Frag-10: subordinate-opener + lowercase-predicate + trailing-
    fragment screens, the yet/thus/where/to/rather/agreement fixes to
    the frag-8/9 spares, the qualifier-only tier backstop, the
    media-filename stat screen, and the drain demotion fix (gate 50m,
    casey-jones / leatherhead / shredder / blackarachnia / devastator
    / ironhide / rodimus-prime / soundwave / starscream /
    ultra-magnus / arcee / galvatron / predaking)."""

    def test_verbatim_subordinate_openers_flagged(self):
        for text in (
            ("as he passes up a chance to kill Wheeljack in order to "
            "save Laserbeak."),
            "As Ironhide ages",
            "especially when anything related to the Kraang is brought up",
        ):
            self.assertIn(
                "subordinate_opener",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_subordinate_opener_controls_survive(self):
        # A subordinate opener WITH a main clause of its own (after a
        # comma, a sentence boundary, or a second subject+verb pair)
        # is whole; so are the excluded openers "once"/"until"
        # (legit limitations / version labels) and "though"/"although"
        # (the frag-8 pinned concessive controls).
        for text in (
            "after Noon his power will begin to decline.",
            ("when the incantation is uttered its effect is the "
            "equivalent of a wish."),
            "Before Crisis, normally Sephiroth lacks a true weakness.",
            "Once per day, he must rest to recover his strength.",
            "If his ring is destroyed, he loses all of his power.",
            ("though he manages to gain some control over this as time "
            "goes on."),
            "though this weakness was overcome, he still fears fire.",
        ):
            self.assertEqual(
                fragment_item_reasons(text, section="weaknesses"), [], text
            )

    def test_verbatim_yet_rather_to_flagged(self):
        for text, reason in (
            (
                ("yet believes himself to be and thus can be overwhelmed "
                "by the stronger mutants they may face. In general"),
                "prose_sentence_shard",
            ),
            (
                "to the point where it could potentially impede his judgement",
                "prose_sentence_shard",
            ),
            (
                ("rather easy to outmaneuver. His lacking intelligence "
                "offers little combat adaptability. As the Constructicons'"),
                "trailing_fragment",
            ),
        ):
            self.assertIn(
                reason,
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_verbatim_where_flagged(self):
        self.assertIn(
            "relative_pronoun_opener",
            fragment_item_reasons(
                "where he is ticklish.", section="weaknesses"
            ),
        )

    def test_verbatim_lowercase_predicates_flagged(self):
        for text in (
            "insane and is very self loathing.",
            ("very short tempered (If something doesn't go his way he "
            "will throw a tantrum). If the allspark shard in his head "
            "is removed"),
        ):
            self.assertIn(
                "lowercase_predicate",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_lowercase_predicate_controls_survive(self):
        # A lowercase predicate WITH a main clause is whole, and a
        # real limitation statement never fires.
        for text in (
            "very strong, he can lift a mountain.",
            "He is very short tempered and throws tantrums.",
            "completely healed, he returns to the fight.",
        ):
            self.assertEqual(
                fragment_item_reasons(text, section="weaknesses"), [], text
            )

    def test_verbatim_trailing_fragments_flagged(self):
        for text in (
            "Devastator is hardly slow. He is",
            ("rather easy to outmaneuver. His lacking intelligence "
            "offers little combat adaptability. As the Constructicons'"),
            ("very short tempered (If something doesn't go his way he "
            "will throw a tantrum). If the allspark shard in his head "
            "is removed"),
        ):
            self.assertIn(
                "trailing_fragment",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_trailing_fragment_controls_survive(self):
        # A multi-sentence item whose final sentence is whole, and a
        # single-sentence item (the screen needs a tail to judge).
        for text in (
            "Devastator is hardly slow. He is still the strongest.",
            "He is weak to fire. When exposed, he burns.",
            "As Ironhide ages",
        ):
            self.assertNotIn(
                "trailing_fragment",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_verbatim_agreement_gerund_flagged(self):
        self.assertIn(
            "prose_sentence_shard",
            fragment_item_reasons(
                "feeling he don't ever live up to Optimus Prime. "
                "Without the Matrix of Leadership",
                section="weaknesses",
            ),
        )

    def test_agreement_controls_survive(self):
        # Standard agreement still counts as a headed/subject-led
        # clause: "he does", "they do". (A gerund-led item never
        # survives on agreement alone -- "feeling he does..." is
        # still a gerund continuation -- and a base-form plural verb
        # like "they live" is not recognized by the headed test, so
        # neither shape is used as a control here.)
        for text in (
            "yet they do face stronger mutants.",
            "yet he does face stronger mutants.",
            "he does not fear him.",
        ):
            self.assertNotIn(
                "prose_sentence_shard",
                fragment_item_reasons(text, section="weaknesses"),
                text,
            )

    def test_frag10_screens_are_weaknesses_only(self):
        for reason, text in (
            ("subordinate_opener", "as he passes up a chance to kill Wheeljack."),
            ("lowercase_predicate", "insane and is very self loathing."),
            ("trailing_fragment", "Devastator is hardly slow. He is"),
        ):
            self.assertNotIn(
                reason,
                fragment_item_reasons(text, section="powers_and_abilities"),
                text,
            )

    def test_verbatim_tiers_flagged(self):
        for text in (
            "likely higher. with swords",
            "At most, possibly far higher",
            "At least, higher with the Heart of Darkness",
            ("At most. higher with Stealth Force, even higher with "
            "Heavy Iron 2.0"),
            "At least, likely higher, even higher with Beast Mode",
        ):
            self.assertIn(
                "qualifier_only_stat",
                boilerplate_reasons(text, scalar=True),
                text,
            )
            self.assertIn(
                "qualifier_only_stat",
                fragment_scalar_reasons(text),
                text,
            )
            self.assertIn(
                "qualifier_only_stat",
                stat_field_rejection_reasons(text),
                text,
            )

    def test_tier_backstop_controls_survive(self):
        # A rating token, a level phrase, or no qualifier at all
        # means the value is real; version digits are not ratings
        # but "Heavy Iron 2.0" only fires as part of a qualifier-only
        # tail, never on its own.
        for text in (
            "At least 8-C",
            "At least Small Building level",
            "Unknown",
            "Varies",
            "8-C, higher with the Moon",
            "Building level, higher with weapons",
            "High 5-A with swords",
            "Low 5-B, likely higher",
        ):
            self.assertNotIn(
                "qualifier_only_stat",
                boilerplate_reasons(text, scalar=True),
                text,
            )

    def test_verbatim_media_range_flagged(self):
        text = (
            "Hundreds of Meters with guns. "
            "SolarBeamRifleDevastation.png "
            "DrillMisslesDevastation.jpg DrillsDevastation.jpg"
        )
        self.assertIn("media_fragment", boilerplate_reasons(text, scalar=True))
        self.assertIn(
            "media_fragment", stat_field_rejection_reasons(text)
        )
        self.assertIn("media_fragment", fragment_scalar_reasons(text))

    def test_media_controls_survive(self):
        # Citation links legitimately contain ".jpg" inside their
        # URLs; only bare filenames fire.
        for text in (
            ("City level+ ([https://imgur.com/a/54gVkly Considered one "
            "of the most powerful Jedi by the beginning of the Clone "
            "Wars]."),
            ("City level ([https://gallery.missdream.org/albums/"
            "scanlation_smoon/smoon_act01/038.jpg Did not seem "
            "impressed by Sailor Moon's Ultimate Attack]."),
            "Hundreds of Meters to Kilometres with guns",
        ):
            self.assertNotIn(
                "media_fragment",
                boilerplate_reasons(text, scalar=True),
                text,
            )

    def test_filter_drops_frag10_debris_keeps_real_weakness(self):
        kept, dropped = filter_list_field_items(
            "yet believes himself to be and thus can be overwhelmed "
            "by the stronger mutants they may face. In general, "
            "especially when anything related to the Kraang is brought "
            "up, where he is ticklish., insane and is very self "
            "loathing., Devastator is hardly slow. He is, As Ironhide "
            "ages, feeling he don't ever live up to Optimus Prime. "
            "Without the Matrix of Leadership, as he passes up a "
            "chance to kill Wheeljack in order to save Laserbeak., "
            "very short tempered (If something doesn't go his way he "
            "will throw a tantrum). If the allspark shard in his head "
            "is removed, to the point where it could potentially "
            "impede his judgement, Is weak to fire",
            section="weaknesses",
        )
        self.assertEqual(kept, "Is weak to fire")
        reasons = [r for d in dropped for r in d["reasons"]]
        for reason in (
            "prose_sentence_shard",
            "subordinate_opener",
            "relative_pronoun_opener",
            "lowercase_predicate",
            "trailing_fragment",
        ):
            self.assertIn(reason, reasons)

    def test_repair_attempt_drops_frag10_debris(self):
        prof = comic_profile("Casey Jones", "Teenage Mutant Ninja Turtles")
        fields = dict(SixthGenRepairPathTests.FIELDS)
        fields["weaknesses"] = (
            "yet believes himself to be and thus can be overwhelmed "
            "by the stronger mutants they may face. In general, "
            "especially when anything related to the Kraang is brought "
            "up, Is weak to fire"
        )
        fields["tier"] = "likely higher. with swords"
        fields["range"] = (
            "Hundreds of Meters with guns. "
            "SolarBeamRifleDevastation.png"
        )
        attempt = SixthGenRepairPathTests()._attempt(prof, fields)
        mapped = attempt_field_map(attempt)
        self.assertEqual(mapped["weaknesses"], "Is weak to fire")
        self.assertNotIn("tier", mapped)
        self.assertNotIn("range", mapped)
        dropped = (attempt.metadata.get("dropped_items") or {}).get(
            "weaknesses"
        ) or []
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("prose_sentence_shard", reasons)
        self.assertIn("subordinate_opener", reasons)
        dropped_scalar = attempt.metadata.get("dropped_scalar_fields") or {}
        self.assertIn("qualifier_only_stat", dropped_scalar.get("tier", []))
        self.assertIn("media_fragment", dropped_scalar.get("range", []))

    def test_demotion_restores_ineligible_reasons(self):
        # Frag-10 drain fix: a profile demoted by
        # apply_primary_profile_state after a promotion had
        # ineligible_reasons=[] left over, which fails schema
        # validation ("ineligible profile requires
        # generation.ineligible_reasons"). Demotion restores the
        # generic reason; a non-empty list is left alone.
        prof = {
            "generation": {"ineligible_reasons": [], "confidence": 0.8},
            "review": {},
        }
        apply_primary_profile_state(prof, primary=None, corroborated=False)
        self.assertEqual(prof["status"], "needs_review")
        self.assertFalse(prof["battle_eligible"])
        self.assertEqual(
            prof["generation"]["ineligible_reasons"], ["needs_review"]
        )
        prof = {
            "generation": {"ineligible_reasons": ["needs_review"]},
            "review": {},
        }
        apply_primary_profile_state(prof, primary=None, corroborated=False)
        self.assertEqual(
            prof["generation"]["ineligible_reasons"], ["needs_review"]
        )

    def test_promotion_still_clears_ineligible_reasons(self):
        # Frag-11: promotion now requires the schema eligibility
        # contract, so the fixture must satisfy it (core stats,
        # usable ability, revision metadata) -- a bare generation
        # dict no longer promotes, by design.
        prof = promotable_profile()
        apply_primary_profile_state(
            prof, primary=None, corroborated=True, force_promotable=True
        )
        self.assertTrue(prof["battle_eligible"])
        self.assertEqual(prof["generation"]["ineligible_reasons"], [])


class EleventhGenFrag11PromotionTests(unittest.TestCase):
    """Frag-11 workstream B: the promotion branch must require the
    schema's full eligibility contract, not usable-text alone."""

    def test_fully_recovered_profile_still_promotes(self):
        prof = promotable_profile()
        apply_primary_profile_state(
            prof, primary=None, corroborated=False, force_promotable=True
        )
        self.assertTrue(prof["battle_eligible"])
        self.assertEqual(prof["status"], "provisional")
        self.assertEqual(prof["profile_type"], "auto_evidence_profile")
        self.assertEqual(prof["generation"]["ineligible_reasons"], [])
        self.assertGreaterEqual(prof["generation"]["confidence"], 0.55)

    def test_promotion_blocked_without_revision_metadata(self):
        # Maliketh shape: approval_blockers=[] yet the CSPW source
        # carries no revision metadata, so the schema contract fails
        # on missing_source_revision_metadata alone. The profile must
        # stay needs_review with non-empty reasons, never eligible.
        prof = promotable_profile()
        for source in prof["sources"]:
            source.pop("revision_id", None)
            source.pop("revision_timestamp", None)
        apply_primary_profile_state(
            prof, primary=None, corroborated=False, force_promotable=True
        )
        self.assertFalse(prof["battle_eligible"])
        self.assertEqual(prof["status"], "needs_review")
        self.assertEqual(prof["profile_type"], "needs_review")
        self.assertTrue(prof["generation"]["ineligible_reasons"])

    def test_promotion_blocked_when_approval_blockers(self):
        # Missing durability text: approval_blockers is non-empty, so
        # no promotion even with revision metadata present.
        prof = promotable_profile()
        prof["power_scale"]["durability"] = {"text": "", "source_ids": []}
        apply_primary_profile_state(
            prof, primary=None, corroborated=False, force_promotable=True
        )
        self.assertFalse(prof["battle_eligible"])
        self.assertTrue(prof["generation"]["ineligible_reasons"])

    def test_tier_only_recovery_not_eligible(self):
        # A tier-only recovery (core stats still missing) must NOT
        # leave the profile eligible, even though tier text merged.
        prof = promotable_profile()
        prof["power_scale"] = {
            "tier": {"text": "9-A", "source_ids": ["src1"]},
        }
        apply_primary_profile_state(
            prof, primary=None, corroborated=False, force_promotable=True
        )
        self.assertFalse(prof["battle_eligible"])
        self.assertEqual(prof["status"], "needs_review")
        self.assertTrue(prof["generation"]["ineligible_reasons"])

    def test_promotion_blocked_when_primary_absent(self):
        # No primary attempt and no force flag: the else branch, as
        # before -- now also the contract-failure path.
        prof = promotable_profile()
        apply_primary_profile_state(prof, primary=None, corroborated=False)
        self.assertFalse(prof["battle_eligible"])
        self.assertEqual(prof["status"], "needs_review")


class EleventhGenFrag11ScreenTests(unittest.TestCase):
    """Frag-11 workstream A: the six gate-50n debris families."""

    # -- (1) label-bleed stats ---------------------------------------
    def test_label_bleed_stat_oryx_verbatim(self):
        for value in (
            "Lifting Strength: Striking Strength:",
            "Standard Equipment: Intelligence: Above Average",
        ):
            self.assertIn(
                "label_bleed_stat",
                boilerplate_reasons(value, scalar=True),
                value,
            )
            self.assertIn(
                "label_bleed_stat",
                stat_field_rejection_reasons(value),
                value,
            )

    def test_label_bleed_stat_spares_real_content_first(self):
        # Calib1b: 5 of 6 stored >=2-label values carry real content
        # before the first label; only the label-led shape is debris.
        for value in (
            ("Massively Hypersonic+ (Blitzed a Level 4 Akuma) "
            "Lifting Strength: Class M"),
            ("Extended Melee Range via sword; Tens of Meters via sword "
            "beams Standard Equipment: The Crissword"),
            "Lifting Strength: Class M",
        ):
            self.assertNotIn(
                "label_bleed_stat",
                boilerplate_reasons(value, scalar=True),
                value,
            )

    # -- (2) bare "<X> ID Types" tab keys ----------------------------
    def test_bare_id_types(self):
        for item in ("Battle ID Types", "Bird ID Types", "Mage ID Types"):
            self.assertIn(
                "section_header", fragment_item_reasons(item), item
            )

    def test_id_types_controls(self):
        for item in (
            "Public Safety ID Badge and Controlled Minions",
            "Fairy ID Type:",
            "Flight",
        ):
            if item == "Fairy ID Type:":
                self.assertIn(
                    "section_header", fragment_item_reasons(item), item
                )
            else:
                self.assertNotIn(
                    "section_header", fragment_item_reasons(item), item
                )

    # -- (3) section headers as items --------------------------------
    def test_tier_baseline_header_items(self):
        for item in (
            "Dark Lord abilities (4-D - Baseline)",
            "Creatures of Chaos (4-D - Baseline)",
            ("Dark Lord abilities (4-D - Baseline Has access to "
            "Dracula's magic due to his powers being a part of the "
            "castle)"),
        ):
            self.assertIn(
                "section_header", fragment_item_reasons(item), item
            )

    def test_baseline_controls(self):
        # name==desc alone must never fire: 131,416 stored items.
        for item in ("Immortality", "Flight", "Large Size"):
            self.assertNotIn(
                "section_header", fragment_item_reasons(item), item
            )

    # -- (4) mid-word truncated items ------------------------------
    def test_midword_truncated_verbatim(self):
        self.assertIn(
            "truncated_item",
            fragment_item_reasons(
                "Absorption (With Healing Drop and Deadly Absorp)"
            ),
        )

    def test_midword_truncated_controls(self):
        for item in (
            "Homing Attack (With Homing Eye and Homing)",
            "Teleportation (Can teleport)",
            "Healing (Can heal allies by cheering on them)",
            "Waterbending (With any phase of water)",
            "Regeneration (Mid-Low via Regen)",
            "Absorption (With Healing Drop and Deadly Absorption)",
        ):
            self.assertNotIn(
                "truncated_item", fragment_item_reasons(item), item
            )

    # -- (5) bare character-name abilities ---------------------------
    def test_bare_proper_name(self):
        self.assertIn(
            "bare_proper_name", fragment_item_reasons("Radagon")
        )

    def test_bare_proper_name_controls(self):
        # Legit bare CSPW ability names (the known FP class) survive.
        for item in ("Flight", "Magic", "Immortality", "Acrobatics", "Teleportation"):
            self.assertNotIn(
                "bare_proper_name", fragment_item_reasons(item), item
            )

    # -- (6i) conjunction orphans: but / yet / so / nor ---------------
    def test_conjunction_orphan_but(self):
        self.assertIn(
            "conjunction_orphan",
            fragment_item_reasons("but after the Night of the black knives"),
        )
        for item in ("yet injured", "so it can reform itself)", "nor air in his armored form"):
            self.assertIn(
                "conjunction_orphan",
                fragment_item_reasons(item),
                item,
            )

    def test_conjunction_orphan_controls(self):
        for item in ("Soul Manipulation", "Flight", "Butcher's Blade"):
            self.assertNotIn(
                "conjunction_orphan",
                fragment_item_reasons(item),
                item,
            )

    # -- (6ii) orphaned tails ----------------------------------------
    def test_orphan_tail_standalone(self):
        for item in ("he was limited.", "it was destroyed."):
            self.assertIn(
                "orphan_tail_clause",
                fragment_item_reasons(item),
                item,
            )

    def test_orphan_tail_controls(self):
        for item in (
            "he was stripped of most of his magic",
            "He is physically blind",
            "He is weak to fire",
        ):
            self.assertNotIn(
                "orphan_tail_clause",
                fragment_item_reasons(item),
                item,
            )

    def test_orphan_tail_sequential(self):
        # The tail drops when it directly follows a dropped
        # conjunction-led fragment, even with a short complement the
        # standalone rule spares.
        kept, dropped, _ = filter_list_field_items_detailed(
            "but after the Night of the black knives, "
            "he was limited to one attack",
            section="powers_and_abilities",
        )
        self.assertEqual(kept, "")
        reasons = [r for d in dropped for r in d["reasons"]]
        self.assertIn("conjunction_orphan", reasons)
        self.assertIn("orphan_tail_clause", reasons)

    # -- (6iii) glued composites -------------------------------------
    def test_glued_composite_verbatim(self):
        self.assertIn(
            "glued_composite",
            fragment_item_reasons(
                "Durability Negation Destined Death lowers and burns HP. "
                "Death Manipulation Maliketh could manipulate Death"
            ),
        )

    def test_glued_composite_controls(self):
        for item in (
            ("Soul Manipulation & Energy Manipulation (With the Grand "
            "Wave and Glow Soul)"),
            ("Sound Manipulation Maliketh's roars can damage and knock "
            "down the player."),
            ("Soul Manipulation Even a small fragment of Destined Death "
            "destroyed Godwyn's soul."),
            ("Energy Manipulation Can fire red energy out of his Black "
            "Blade."),
        ):
            self.assertNotIn(
                "glued_composite", fragment_item_reasons(item), item
            )

    # -- (6iv) description bleed -------------------------------------
    def test_section_header_bleed(self):
        for item in (
            ("Frost Damage and the Blasphemous Claw Feats: Can utilize "
            "Destined Death to kill Immortals"),
            ("Forcefield Creation (Via Protective FieldCastlevania: "
            "Curse of Darkness Bradygames official strategy guide "
            "page 102) Dark Lord resistances (4-D - Baseline)"),
        ):
            self.assertIn(
                "section_header", fragment_item_reasons(item), item
            )

    def test_section_header_bleed_controls(self):
        for item in (
            "Weak to Dragon and Fairy-type moves.",
            "Psychic Abilities (Telekinesis, Telepathy)",
            "Forcefield Creation (Via Guard)",
        ):
            self.assertNotIn(
                "section_header", fragment_item_reasons(item), item
            )

    # -- verbatim families end-to-end at the merge choke point -------
    def test_maliketh_pieces_filtered(self):
        kept, _dropped, _ = filter_list_field_items_detailed(
            "Immortality Negation Can kill immortals such as Marika, "
            "Radagon, and Elden Beast (Via Destined Death) | Sound "
            "Manipulation Maliketh's roars can damage and knock down "
            "the player. | Durability Negation Destined Death lowers "
            "and burns HP. Death Manipulation Maliketh could "
            "manipulate Death, but after the Night of the black "
            "knives, he was limited. | Soul Manipulation Even a small "
            "fragment of Destined Death destroyed Godwyn's soul.",
            section="powers_and_abilities",
        )
        self.assertNotIn("Radagon", kept)
        self.assertNotIn("but after the Night", kept)
        self.assertNotIn("he was limited", kept)
        self.assertNotIn("Durability Negation Destined Death", kept)
        self.assertIn("Sound Manipulation", kept)
        self.assertIn("Soul Manipulation", kept)

    def test_isaac_pieces_filtered(self):
        kept, _dropped, _ = filter_list_field_items_detailed(
            "Dark Lord abilities (4-D - Baseline), Extrasensory "
            "Perception (Can sense Demonic Energy), Immortality, "
            "Absorption (With Healing Drop and Deadly Absorp), "
            "Battle ID Types, Bird ID Types, Mage ID Types",
            section="powers_and_abilities",
        )
        self.assertNotIn("Dark Lord abilities", kept)
        self.assertNotIn("Deadly Absorp", kept)
        self.assertNotIn("Battle ID Types", kept)
        self.assertNotIn("Bird ID Types", kept)
        self.assertNotIn("Mage ID Types", kept)
        self.assertIn("Extrasensory Perception", kept)
        self.assertIn("Immortality", kept)


class TwelfthGenFrag12ScreenTests(unittest.TestCase):
    """Frag-12 workstream: the frag-11-quarantined debris families.

    Verbatim items come from the frag-11 audit corpus
    (/opt/referee/data/frag12_20261025/corpus.json) and the calibration
    rounds (bottlenecks/frag12_calib{1,2,3}.py). Controls are the
    legit items calibration showed must survive.
    """

    # -- G1a/G1c label fragments --------------------------------------
    def test_label_fragment_verbatim(self):
        for item in (
            "Chapter VII",
            "Act III: Night White",
            "Season 1",
            "Season 4",
            "Episode 2",
            "Episode 8",
            'Episode 2 "ARC Troopers" While defeated',
            "chapter 1",
            "chapter 3",
        ):
            self.assertIn(
                "label_fragment", fragment_item_reasons(item), item
            )

    def test_label_fragment_controls_survive(self):
        # A label glued to substantive prose is kept -- the label is
        # noise, the content is real (grievous Episode 9, jiji Ch. 40,
        # nanami Ch. 120, sauron Ch. 19).
        for item in (
            ('Episode 9 "Grievous Intrigue" likely helped by the '
            "unpredictability of this contortion."),
            "Chapter 40 When he uses The Evil Gun technique",
            "Chapter 120 after his body was stabbed several times",
            ("Chapter 19: OF BEREN AND LÚTHIEN It is even described "
            "that Sauron eventually achieved Morgoth's feat"),
            ("he is highly susceptible to the Scourge Virus."
            "Invincible Season 4"),
        ):
            self.assertNotIn(
                "label_fragment",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    # -- G1b quoted-title tail ----------------------------------------
    def test_quoted_title_fragment_verbatim(self):
        self.assertIn(
            "quoted_title_fragment",
            fragment_item_reasons('"Season Four Finale" Additionally'),
        )

    def test_quoted_title_controls_survive(self):
        # Quoted names + a noun are legitimate items (calib1 FPs).
        for item in (
            '"Tsubakuro" shuriken',
            '"Last Breath" Sword',
            '"the legendary hitman" himself',
        ):
            self.assertNotIn(
                "quoted_title_fragment", fragment_item_reasons(item), item
            )

    # -- G2 list intro -------------------------------------------------
    def test_list_intro_verbatim(self):
        for item in (
            "Black Noir has the following",
            "Starlight has the following",
            "Stormfront has the following",
            "Kimiko has the following",
        ):
            self.assertIn(
                "list_intro_fragment",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    def test_list_intro_controls_survive(self):
        # A real weakness sentence that merely contains the phrase.
        self.assertNotIn(
            "list_intro_fragment",
            fragment_item_reasons(
                "He has the following weaknesses: fire and ice.",
                section="weaknesses",
            ),
        )

    # -- G3 equipment fragment -----------------------------------------
    def test_equipment_fragment_verbatim(self):
        self.assertIn(
            "equipment_in_weaknesses",
            fragment_item_reasons(
                "Amethyst's upgraded whip.", section="weaknesses"
            ),
        )

    def test_equipment_controls_survive(self):
        self.assertNotIn(
            "equipment_in_weaknesses",
            fragment_item_reasons(
                "Superman's cape can be used against him.",
                section="weaknesses",
            ),
        )

    # -- G4a ability headers in weaknesses -----------------------------
    def test_ability_header_verbatim(self):
        for item in (
            ("Rugal can create a ball of electricity around his body "
            "and then fires it. *Dark Barrier: Rugal can create a "
            "barrier that"),
            ("Vega is able to adhere on a wall for a brief moment and "
            "gain an additional jump. *Back Slash: Vega somersaults "
            "backwards"),
            ("she can use multiple shards to revolve around herself. "
            "*Thundaga: Celes calls down contracting Lightning Bolts "
            "around her"),
        ):
            self.assertIn(
                "ability_header_in_weaknesses",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    def test_ability_header_controls_survive(self):
        # A legit structured weakness list: element headers with
        # limitation language. Page-structure headers are excluded.
        self.assertNotIn(
            "ability_header_in_weaknesses",
            fragment_item_reasons(
                "Fire: weak to fire. Ice: weak to ice.",
                section="weaknesses",
            ),
        )
        self.assertNotIn(
            "ability_header_in_weaknesses",
            fragment_item_reasons(
                "Victories: Losses: Inconclusive:", section="weaknesses"
            ),
        )

    # -- G4b capability without limitation -------------------------------
    def test_capability_verbatim(self):
        for item in (
            ("Iori can control fire. He can create a bright purple "
            "fire from thin air"),
            ("Dialga can control time. Examples include causing time "
            "loops"),
            ("he's able to take their form and use any of their "
            "abilities. For example"),
            ("Steven can summon Rose's shield and can expand his "
            "bubble to protect others"),
        ):
            self.assertIn(
                "capability_in_weaknesses",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    def test_capability_controls_survive(self):
        # The four genuine-limitation steven items: each carries a
        # limitation marker (little control / not work / cannot /
        # only + strain) and must pass.
        for item in (
            "Steven had little control over his powers",
            "causing his abilities to not work properly",
            ("his half-human nature means he cannot use his gem "
            "powers fully"),
            ("he can only do this for a certain amount of time and "
            "his half-human nature puts more of a strain on his "
            "body than it would a Gem"),
            "He can regenerate, but the process is slow and painful",
            "He is bound to the Underworld",
            "and will die if he stays in the mortal realm for long",
            "he is vulnerable to high-frequency sounds",
        ):
            self.assertNotIn(
                "capability_in_weaknesses",
                fragment_item_reasons(item, section="weaknesses"),
                item,
            )

    # -- G5 placeholder --------------------------------------------------
    def test_capability_pronoun_object_exempt(self):
        # Established control: whole clauses ending on a pronoun
        # object are legit weaknesses (test_headed_clauses_ending_on_
        # pronouns_pass). A concrete object anywhere defeats it.
        self.assertNotIn(
            "capability_in_weaknesses",
            fragment_item_reasons(
                "Whitesnake can control them", section="weaknesses"
            ),
        )
        self.assertIn(
            "capability_in_weaknesses",
            fragment_item_reasons(
                "Whitesnake can control them and can create discs "
                "from people's souls",
                section="weaknesses",
            ),
        )

    def test_placeholder_verbatim(self):
        for item in ("None noted.", "N/A", "Unknown", "None"):
            self.assertIn(
                "placeholder_item", fragment_item_reasons(item), item
            )

    def test_placeholder_controls_survive(self):
        self.assertNotIn(
            "placeholder_item",
            fragment_item_reasons("None notable", section="weaknesses"),
        )
        self.assertNotIn(
            "placeholder_item",
            fragment_item_reasons(
                "Unknown energy source", section="weaknesses"
            ),
        )

    # -- G screens are section-scoped correctly -------------------------
    def test_g4_screens_are_weaknesses_only(self):
        # The same capability sentence as an ABILITY is legitimate.
        self.assertNotIn(
            "capability_in_weaknesses",
            fragment_item_reasons(
                "Iori can control fire. He can create a bright "
                "purple fire from thin air",
                section="abilities",
            ),
        )
        self.assertNotIn(
            "ability_header_in_weaknesses",
            fragment_item_reasons(
                "Rugal can create a ball of electricity. *Dark "
                "Barrier: Rugal can create a barrier",
                section="abilities",
            ),
        )

    def test_filter_drops_frag12_debris_keeps_real_weakness(self):
        kept, _dropped, _ = filter_list_field_items_detailed(
            "Season 1 | Black Noir has the following | Amethyst's "
            "upgraded whip. | None noted. | Iori can control fire. "
            "He can create a bright purple fire from thin air | "
            "he is vulnerable to high-frequency sounds | Steven had "
            "little control over his powers",
            section="weaknesses",
        )
        self.assertNotIn("Season 1", kept)
        self.assertNotIn("has the following", kept)
        self.assertNotIn("upgraded whip", kept)
        self.assertNotIn("None noted", kept)
        self.assertNotIn("bright purple fire", kept)
        self.assertIn("high-frequency sounds", kept)
        self.assertIn("little control", kept)


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
            ("etc. You can judge a person's power by their feats. "
            "Notable Attacks/Techniques: A list of some abilities "
            "the character has"),
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
            ("This profile is so far from done but i am sleepy "
            "(Last issue recorded Issue #14 of Animal Man 1988)"),
            ("A powerful mage whom in his regular form could combat "
            "Nezha) This is so far from done but i am sleepy "
            "(Last issue recorded Issue #14 of Animal Man 1988)"),
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


if __name__ == "__main__":
    unittest.main()
