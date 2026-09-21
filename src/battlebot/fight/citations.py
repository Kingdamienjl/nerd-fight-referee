"""Compact source references for matchup evidence, with URLs kept out of prompts."""
import re
from urllib.parse import urlsplit

WIKI_LAYOUT = re.compile(r"\{\{|\}\}|#tag:|\b(?:scroll|visible|padding|content|border)\s*=|\btabber\b", re.I)

def clean_profile_text(value, limit=None):
    """Reject broken harvested fragments without rewriting substantive claims."""
    text = str(value or "")
    if WIKI_LAYOUT.search(text) or not re.search(r"\w", text):
        return ""
    text = re.sub(r"^[A-Za-z0-9 /_'.-]{1,60}=\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -,:;|\n\t")
    if limit and len(text) > limit:
        text = text[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return text

def power_summary(value, limit=260):
    raw = str(value or "")
    if WIKI_LAYOUT.search(raw) or re.search(r"(?:Chapter|Issue)\s*\d+\s*>", raw, re.I):
        raw = re.sub(r"\{\{Tabber\|?", "", raw, flags=re.I)
        raw = re.sub(r"\}\}", "", raw)
    if "|" in raw:
        parts = [p.strip() for p in raw.split("|") if p.strip() and not p.strip().startswith("{{")]
        if parts:
            raw = parts[0]
    raw = re.sub(r"^[A-Za-z0-9 /_'.-]{1,60}=\s*", "", raw)
    cleaned = clean_profile_text(raw, limit)
    return cleaned or clean_profile_text(value, limit)


def source_catalog(packet):
    catalog=[]
    for side in ('contender_a','contender_b'):
        c=packet.get(side) or {}
        for source in c.get('sources') or []:
            url=str(source.get('url') or '')
            parsed=urlsplit(url)
            if parsed.scheme not in ('http','https') or not parsed.netloc:
                continue
            catalog.append({'number':len(catalog)+1,'side':side,'id':source.get('id'),
                            'title':source.get('title') or 'Source','url':url,
                            'fighter':c.get('canonical_name') or side,'revision':source.get('revision_id')})
    return catalog

def reference_numbers(catalog,side,ids):
    return [s['number'] for s in catalog if s['side']==side and s['id'] in (ids or [])]

def linked_citations(text,packet):
    catalog={s['number']:s for s in source_catalog(packet)}
    def replace(match):
        number=int(match.group(1));source=catalog.get(number)
        if not source:
            return '[source unavailable]'
        url=source['url'].replace('(', '%28').replace(')', '%29').replace(' ', '%20')
        return f'[{number}]({url})'
    return re.sub(r'\[(\d+)\](?!\()',replace,str(text))

def source_panel(packet):
    lines=[]
    for s in source_catalog(packet):
        title=str(s['title']).replace('[','').replace(']','')
        line=f"[{s['number']}] {s['fighter']} — {title}"
        lines.append(linked_citations(line,packet)+(f" • revision {s['revision']}" if s['revision'] else ''))
    return '\n\n'.join(lines) or 'No linked sources supplied for this matchup.'

def evidence_brief(packet):
    catalog=source_catalog(packet);lines=[]
    for side in ('contender_a','contender_b'):
        c=packet.get(side) or {};lines.append('**'+str(c.get('canonical_name') or 'Fighter')+'**')
        for axis in ('speed','attack_potency','durability'):
            value=(c.get('power_scale') or {}).get(axis)
            if value:
                numbers=reference_numbers(catalog,side,(c.get('power_scale_source_ids') or {}).get(axis,[]))
                refs=' '.join(f'[{n}]' for n in numbers)
                lines.append(f"{axis.replace('_',' ').title()}: {power_summary(value)} {refs}")
        shown = 0
        for item in c.get('abilities') or []:
            name = clean_profile_text(item.get('name'), 100)
            if not name:
                continue
            refs=' '.join(f'[{n}]' for n in reference_numbers(catalog,side,item.get('source_ids',[])))
            description = clean_profile_text(item.get('description') or '', 200)
            body = name if not description or description == name else f"{name}: {description}"
            lines.append(f"• {body} {refs}".rstrip())
            shown += 1
            if shown == 5:
                break
        if not shown:
            lines.append("Ability evidence needs re-extraction; no usable ability entries were supplied.")
    return linked_citations('\n'.join(lines),packet)
