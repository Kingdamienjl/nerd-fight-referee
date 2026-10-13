import asyncio
import sys

sys.path.insert(0, "/opt/referee/src")
import battlebot.common.qdrant as q


async def main():
    avail = await q.is_qdrant_available()
    print(f"Referee Qdrant reachable on port 6335: {avail}")
    assert avail, "Qdrant is not reachable!"

    # Ensure collection
    created = await q.ensure_collection(q.COLLECTION_FEATS, vector_size=4)
    print(f"Collection '{q.COLLECTION_FEATS}' created/ensured: {created}")

    # Verify namespace security check
    try:
        await q.ensure_collection("athena_brain_collection")
        print("FAILED: Did not catch foreign collection access!")
        sys.exit(1)
    except ValueError as e:
        print(f"SUCCESS: Foreign collection access blocked correctly: {e}")

    collections = await q.list_referee_collections()
    print(f"Active Referee collections: {collections}")


if __name__ == "__main__":
    asyncio.run(main())
