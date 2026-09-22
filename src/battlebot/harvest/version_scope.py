"""Extract explicitly labelled source versions; never infer ability inheritance."""
import copy
import re
from battlebot.profiles.readiness import assess_readiness


def labelled_section(text, selected, labels):
    """Return only a block headed with the selected source key and an equals sign."""
    pattern = re.compile(r'(?:^|\|)\s*(' + '|'.join(re.escape(x) for x in sorted(labels, key=len, reverse=True)) + r')\s*=\s*', re.I)
    matches = list(pattern.finditer(text or ''))
    found=[]
    for i,match in enumerate(matches):
        if match.group(1).casefold() == selected.casefold():
            found.append((text or '')[match.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip())
    return found[0] if len(found)==1 else None


def scope_extracted_fields(fields, selected):
    raw = re.split(r'(?i)\b(?:Name|Origin|Age|Gender|Classification)\s*:', fields.get('keys') or '')[0]
    labels=[x.strip() for x in raw.split('|') if x.strip()]
    if not 1 <= len(labels) <= 16 or labels.count(selected) != 1:
        return None
    scoped={'keys':selected, 'origin':fields.get('origin')}
    for axis in ('tier','attack_potency','speed','durability','range','stamina','intelligence','lifting_strength','striking_strength'):
        text=fields.get(axis) or ''
        explicit=labelled_section(text,selected,labels)
        parts=[x.strip() for x in text.split('|')]
        if explicit:
            scoped[axis]=explicit
        elif len(parts)==len(labels):
            scoped[axis]=parts[labels.index(selected)]
        elif len(labels)==1:
            scoped[axis]=text
        # A shared stat without an explicit scope is left unknown for multi-key sources.
    for section in ('powers_and_abilities','standard_equipment','weaknesses'):
        explicit=labelled_section(fields.get(section) or '',selected,labels)
        if explicit:scoped[section]=explicit
        elif len(labels)==1:scoped[section]=fields.get(section) or ''
    if not all(scoped.get(k) for k in ('attack_potency','speed','durability','powers_and_abilities')):
        return None
    return scoped
