import asyncio, sys
sys.path.insert(0, "/app/src"); sys.path.insert(0, "/app")
from battlebot.review import queue_worker, service
n = asyncio.run(queue_worker.import_generated_profiles(service.DEFAULT_GENERATED_DIR, database_url=None))
print("imported/updated:", n)
