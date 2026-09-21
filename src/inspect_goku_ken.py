import asyncio
import httpx
import re

def clean_wikitext_abilities(raw_text: str) -> list[str]:
    # Extract all bulleted lines or bold bracketed abilities
    abilities = []
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", raw_text)
    
    # Match bullet points: * [[Ability]] or *'''[[Ability]]''' or * Ability
    for line in text.splitlines():
        line = line.strip()
        # Look for lines starting with *
        if re.match(r"^\*+\s*", line):
            # Clean off leading asterisks and whitespace
            item = re.sub(r"^\*+\s*", "", line).strip()
            # Clean wikilinks [[Target|Display]] -> Display or [[Target]] -> Target
            item = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", item)
            # Clean bold/italics
            item = re.sub(r"'{2,5}", "", item)
            # Remove mediawiki templates like {{Border|...}} or {{!}}
            item = re.sub(r"\{\{[^{}]*\}\}", "", item)
            item = item.replace("{{!}}", "").replace("|-|", "").strip()
            # Drop tabber headers or parameters
            if re.search(r"(?i)^(?:border|scroll|visible|padding|content|title|width)\s*=", item):
                continue
            if re.search(r"(?i)#tag:tabber|^tabber$", item):
                continue
            if item.endswith("▾=") or item.endswith("="):
                continue
            if len(item) < 3 or len(item) > 150:
                continue
            # Check if it looks like an ability
            if item not in abilities:
                abilities.append(item)
    return abilities

async def main():
    async with httpx.AsyncClient() as client:
        r = await client.get("https://vsbattles.fandom.com/api.php", params={
            "action": "query",
            "prop": "revisions",
            "titles": "Son_Goku_(DBS_Manga)",
            "rvprop": "content",
            "format": "json"
        }, headers={"User-Agent": "NerdRefereeBot/1.0"})
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            content = page.get("revisions", [{}])[0].get("*", "")
            # Find Powers and Abilities block
            idx = content.find("Powers and Abilities")
            if idx != -1:
                # take the next 15000 characters
                p_text = content[idx:idx+25000]
                # stop at next major section like Attack Potency or Standard Equipment
                stop = re.search(r"\n\s*(?:'''(?:Attack Potency|Standard Equipment|Tier|Speed|Durability):?'''|==)", p_text)
                if stop:
                    p_text = p_text[:stop.start()]
                cleaned = clean_wikitext_abilities(p_text)
                print(f"Extracted {len(cleaned)} abilities for Goku:")
                for a in cleaned[:25]:
                    print("  -", a)

if __name__ == "__main__":
    asyncio.run(main())
