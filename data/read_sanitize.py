import sys
sys.path.insert(0, "/app/src")
import inspect
from battlebot.review import service
src = inspect.getsource(service.sanitize_generated_profile)
print(src[1500:4200])
