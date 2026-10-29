"""Unit tests for the Fix A evidence-recovery guard.

Cases are calibrated on the four merges that went wrong in the first
recovery run (Caiman / Yoru / Tai Kamiya / Galatea) plus the fanon-page
shapes that recovered correctly (Korosensei, Shinobu Kocho).
"""

import unittest

from battlebot.review.auto_repair import (
    _guard_name_match,
    attempt_field_map,
    attempt_from_result,
    bare_qualifier_reasons,
    boilerplate_reasons,
    clean_item_tails,
    continuity_check,
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
        for item in (
            "Weak to Dragon",
            "Vulnerable to Dragon",
            "special defense",
            "rendering them berserk",
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

    DCAU_CATEGORIES = ["DC Animated Universe", "Characters", "Tier 9"]

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

    FIELDS = {
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

    FIELDS = {
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
            "Several meters with energy blasts (Can snipe targets "
            "from rooftops across the city)",
            "Building level (Destroyed a warehouse with a single strike)",
            "The character's armor plating shrugs off anti-tank fire",
        ):
            self.assertEqual(template_stat_reasons(value), [], value)

    def test_legit_stat_sentences_survive_full_screen(self):
        for value in (
            "Massively Hypersonic+",
            "Standard melee range",
            "Several meters with energy blasts (Can snipe targets "
            "from rooftops across the city)",
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

    FIELDS = {
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
            "At least Small Building level (Destroyed a warehouse "
            "with a single strike)",
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
            "At least Small Building level (Destroyed a warehouse "
            "with a single strike)",
            "At least 8-C, likely higher",
            "Massively Hypersonic+",
            "Standard melee range",
        ):
            self.assertEqual(stat_field_rejection_reasons(value), [], value)


class FourthGenRepairPathTests(unittest.TestCase):
    """Both fourth-generation screens at the repair choke point."""

    FIELDS = {
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


if __name__ == "__main__":
    unittest.main()
