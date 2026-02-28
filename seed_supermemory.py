"""
Seed Supermemory with existing volume data overnight.
Run: python seed_supermemory.py
Requires: SUPERMEMORY_API_KEY environment variable
"""
import json
import os
import time
from pathlib import Path

try:
    from supermemory import Supermemory
except ImportError:
    print("Install supermemory: pip install supermemory")
    raise SystemExit(1)

api_key = os.environ.get("SUPERMEMORY_API_KEY")
if not api_key:
    print("Error: SUPERMEMORY_API_KEY environment variable not set")
    raise SystemExit(1)

client = Supermemory(api_key=api_key)

# Point this at your local copy of the volume data, or run on Modal
RAW_PATH = Path(os.environ.get("RAW_PATH", "./data/raw"))
if not RAW_PATH.exists():
    print(f"Error: {RAW_PATH} does not exist. Set RAW_PATH env var or mount the volume.")
    raise SystemExit(1)

count = 0
errors = 0

for f in RAW_PATH.rglob("*.json"):
    try:
        d = json.loads(f.read_text())
        geo = d.get("geo", {})
        client.add(
            content=f"{d.get('title', '')}\n\n{d.get('content', '')}"[:10000],
            container_tag="chicago_data",
            custom_id=d.get("id", f.stem),
            metadata={
                "source": d.get("source", "unknown"),
                "neighborhood": geo.get("neighborhood", ""),
                "ward": str(geo.get("ward", "")),
            },
        )
        count += 1
        if count % 50 == 0:
            print(f"Seeded {count} docs...")
            time.sleep(1)  # rate limit courtesy
    except Exception as e:
        errors += 1
        print(f"Error: {f.name}: {e}")

print(f"Done: {count} docs seeded to Supermemory ({errors} errors)")
