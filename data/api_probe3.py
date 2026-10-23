import inspect
import sys

sys.path.insert(0, "/app/src")
from battlebot.review import auto_repair as ar

mw = ar.mediawiki
print("mediawiki_api_from_url sig:", inspect.signature(mw.mediawiki_api_from_url))
print("from apollo url:", mw.mediawiki_api_from_url(
    "https://vsbattles.fandom.com/wiki/Apollo_%28Post-Crisis%29"))
print("resolve_mediawiki_api_url sig:", inspect.signature(mw.resolve_mediawiki_api_url))
print("fetch_title_fields sig:", inspect.signature(mw.fetch_title_fields))
print(inspect.getsource(mw.fetch_title_fields)[:1200])
