import time
import urllib.parse
import urllib.request

url = "https://vsbattles.fandom.com/api.php?" + urllib.parse.urlencode({
    "action": "query", "format": "json", "titles": "Apollo (Post-Crisis)",
    "redirects": "1", "prop": "info", "inprop": "url"})
t = time.time()
try:
    req = urllib.request.Request(url, headers={"User-Agent": "probe/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        body = r.read()[:200]
    print("OK", round(time.time() - t, 2), body[:150])
except Exception as e:
    print("FAIL", round(time.time() - t, 2), type(e).__name__, e)
