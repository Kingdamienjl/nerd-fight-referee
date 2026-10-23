import asyncio, logging, sys
sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.INFO, format="LOG %(levelname)s %(message)s")
import requests
from battlebot.harvest.fallback_parsers import (
    run_parse_fallback_chain, parse_with_wikitextparser, extract_from_rendered_html,
)

API = "https://vsbattles.fandom.com/api.php"
H = {"User-Agent": "ai-nerd-fight-bot/0.1"}

r = requests.get(API, params={"action": "query", "prop": "revisions", "rvprop": "content",
                              "rvslots": "main", "format": "json", "titles": "Anos Voldigoad"},
                 headers=H, timeout=60)
pages = r.json()["query"]["pages"]
wikitext = next(iter(pages.values()))["revisions"][0]["slots"]["main"]["*"]
print(f"wikitext bytes: {len(wikitext)}")

def fetch_html_sync():
    rr = requests.get(API, params={"action": "parse", "page": "Anos Voldigoad",
                                   "prop": "text", "format": "json"}, headers=H, timeout=60)
    return rr.json()["parse"]["text"]["*"]

html = fetch_html_sync()
print(f"rendered html bytes: {len(html)}")

async def fetch_html():
    return html

res = asyncio.run(run_parse_fallback_chain(
    wikitext=wikitext, title="Anos Voldigoad", fetch_rendered_html=fetch_html))
print("CHAIN parser_used:", res["parser_used"], "| method:", res["extraction_method"],
      "| used_rendered_html:", res["used_rendered_html"])
print("CHAIN fields:", sorted(res["fields"].keys()))

wtp = parse_with_wikitextparser(wikitext)
print("STEP2 wikitextparser direct: fields =", sorted(wtp.keys()))
hf = extract_from_rendered_html(html)
print("STEP3 rendered-html direct: fields =", sorted(hf.keys()))
print("VERIFY DONE")
