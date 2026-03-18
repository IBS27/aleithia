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

# Point this at your local copy of the volume data, or run on Modal.
project_root = Path(__file__).resolve().parent.parent
default_raw_path = (project_root / "data" / "raw").resolve()
raw_override = os.environ.get("RAW_PATH", "").strip()
shared_raw_override = os.environ.get("ALEITHIA_RAW_DATA_DIR", "").strip()
data_root = os.environ.get("ALEITHIA_DATA_ROOT", "").strip()

if raw_override:
    RAW_PATH = Path(raw_override).expanduser().resolve()
elif shared_raw_override:
    RAW_PATH = Path(shared_raw_override).expanduser().resolve()
elif data_root:
    RAW_PATH = Path(data_root).expanduser().resolve() / "raw"
else:
    RAW_PATH = default_raw_path

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
