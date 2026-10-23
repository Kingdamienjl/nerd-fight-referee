import inspect
import sys

sys.path.insert(0, "/app/src")
from battlebot.review import auto_repair as ar

print("mediawiki attr:", type(ar.mediawiki))
mw = ar.mediawiki
if hasattr(mw, "__file__"):
    print("file:", mw.__file__)
    print("funcs:", [n for n in dir(mw) if not n.startswith("_")][:40])
print("mediawiki_candidate sig:", inspect.signature(ar.mediawiki_candidate))
print("normalized_identity_text('Apollo (Post-Crisis) DC Comics!') ->",
      repr(ar.normalized_identity_text("Apollo (Post-Crisis) DC Comics!")))
src = inspect.getsource(ar.mediawiki_candidate)
print(src[:1500])
