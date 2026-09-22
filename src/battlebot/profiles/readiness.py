"""Structural readiness, distinct from independent factual/source verification."""
import re
from urllib.parse import urlsplit
from battlebot.profiles.evidence_quality import evidence_quality_blockers, usable_item


def assess_readiness(profile):
    blockers = evidence_quality_blockers(profile)
    name = str(profile.get('name') or '').casefold()
    franchise = str(profile.get('franchise') or '').casefold()
    dc = ('dc comics', 'post-crisis', 'post-flashpoint', 'new 52', 'dceu')
    marvel = ('marvel comics', 'earth-616', 'marvel cinematic universe', 'mcu')
    if any(token in name for token in dc) and 'dc' not in franchise:
        blockers.append('identity_mismatch:dc_continuity')
    if any(token in name for token in marvel) and 'marvel' not in franchise:
        blockers.append('identity_mismatch:marvel_continuity')
    # Legacy comma splitting can detach defensive qualifiers and parentheses.
    # Do not let those fragments become usable attack evidence.
    for item in profile.get('abilities') or []:
        if not isinstance(item, dict):
            continue
        description = str(item.get('description') or item.get('name') or '')
        depth = 0
        malformed = False
        for char in description:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                malformed = malformed or depth < 0
        if malformed or depth:
            blockers.append('fragmented_ability_evidence')
        if re.search(r'(?i)\b(?:resistances? to|resistant to|immunity to|immune to)\b', description):
            blockers.append('unclassified_defensive_evidence')
    source_entries = [s for s in profile.get('sources') or [] if isinstance(s, dict)]
    by_id = {}
    for source in source_entries:
        source_id = source.get('id')
        if source_id in by_id and by_id[source_id] != source.get('url'):
            blockers.append('ambiguous_source_identity')
        by_id[source_id] = source.get('url')
    sources = {s.get('id') for s in profile.get('sources') or [] if isinstance(s, dict)
               and urlsplit(str(s.get('url') or '')).scheme in ('http', 'https')
               and urlsplit(str(s.get('url') or '')).netloc}
    if not sources:
        blockers.append('missing_linked_sources')
    for axis in ('attack_potency', 'speed', 'durability'):
        entry = (profile.get('power_scale') or {}).get(axis) or {}
        text = entry.get('text') if isinstance(entry, dict) else entry
        if not text:
            blockers.append('missing_' + axis)
        elif '|' in str(text):
            blockers.append('unresolved_version_scope:' + axis)
        if not isinstance(entry, dict) or not (set(entry.get('source_ids') or []) & sources):
            blockers.append('unlinked_stat:' + axis)
    linked = [a for a in profile.get('abilities') or [] if isinstance(a, dict) and usable_item(a)
              and set(a.get('source_ids') or []) & sources]
    if not linked:
        blockers.append('missing_clean_linked_ability')
    forms = [f for f in profile.get('forms') or [] if isinstance(f, dict) and f.get('source_field') == 'keys']
    if len(forms) > 1 and not profile.get('version_scope', {}).get('evidence_scoped'):
        blockers.append('unresolved_version_scope:multiple_source_keys')
    blockers = sorted(set(blockers))
    return {'level': 'provisional' if blockers else 'structurally_ready',
            'battle_ready': not blockers, 'blockers': blockers,
            'source_verified': False, 'policy_version': '2026-09-22'}
