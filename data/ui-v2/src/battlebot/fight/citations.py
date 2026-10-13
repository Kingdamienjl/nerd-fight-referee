"""Compact source references for matchup evidence, with URLs kept out of prompts."""
import re
from urllib.parse import urlsplit

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
                lines.append(f"{axis.replace('_',' ').title()}: {str(value)[:260]} {refs}")
        for item in (c.get('abilities') or [])[:5]:
            refs=' '.join(f'[{n}]' for n in reference_numbers(catalog,side,item.get('source_ids',[])))
            lines.append(f"• {item.get('name') or 'Ability'}: {str(item.get('description') or '')[:200]} {refs}")
    return linked_citations('\n'.join(lines),packet)
