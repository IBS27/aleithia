"""City Knowledge Graph — NetworkX MultiDiGraph construction and serialization."""
import math
from datetime import datetime, timezone

import modal

from backend.shared_data import get_processed_data_dir, get_raw_data_dir, iter_files, load_json_file, write_json_file
from modal_app.volume import app, volume, graph_image, VOLUME_MOUNT
from modal_app.common import CHICAGO_NEIGHBORHOODS, NEIGHBORHOOD_CENTROIDS, detect_neighborhood


@app.function(
    image=graph_image,
    volumes={VOLUME_MOUNT: volume},
    timeout=300,
)
def build_city_graph():
    """Build full city knowledge graph from enriched docs on volume."""
    import networkx as nx

    volume.reload()
    G = nx.MultiDiGraph()

    # ── 1. Neighborhood nodes ──
    for nb in CHICAGO_NEIGHBORHOODS:
        if nb in NEIGHBORHOOD_CENTROIDS:
            lat, lng = NEIGHBORHOOD_CENTROIDS[nb]
            G.add_node(f"nb:{nb}", type="neighborhood", label=nb, lat=lat, lng=lng, size=40)

    # ── 2. Scan enriched docs for entities ──
    enriched_dir = get_processed_data_dir() / "enriched"
    regulations: dict[str, dict] = {}
    entities: dict[str, dict] = {}
    business_types: dict[str, dict] = {}

    for f in iter_files(enriched_dir, pattern="*.json"):
        try:
            doc = load_json_file(f, default=None)
            if not isinstance(doc, dict):
                continue
        except Exception:
            continue

        nb = doc.get("geo", {}).get("neighborhood", "")
        source = doc.get("source", "")
        title = doc.get("title", "")
        content = doc.get("content", "")
        meta = doc.get("metadata", {})
        timestamp_str = doc.get("timestamp", "")

        # If no geo neighborhood, try to detect from content/title
        if not nb:
            nb = detect_neighborhood(f"{title} {content}")

        # Age decay factor (7-day half-life)
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
        except Exception:
            age_days = 30
        decay = math.exp(-age_days / 7)

        # Regulation nodes from politics + federal_register
        if source in ("politics", "federal_register") and title:
            reg_id = f"reg:{title[:50].replace(' ', '-').lower()}"
            if reg_id not in regulations:
                regulations[reg_id] = {"label": title[:60], "neighborhoods": set(), "count": 0, "decay_sum": 0}
            regulations[reg_id]["count"] += 1
            regulations[reg_id]["decay_sum"] += decay
            if nb:
                regulations[reg_id]["neighborhoods"].add(nb)

        # Entity nodes from reviews + news
        if source in ("news", "yelp", "google_places"):
            entity_name = meta.get("business_name") or meta.get("source_name") or ""
            if entity_name and len(entity_name) > 2:
                ent_id = f"ent:{entity_name[:40].replace(' ', '-').lower()}"
                if ent_id not in entities:
                    entities[ent_id] = {"label": entity_name[:40], "neighborhoods": set(), "sentiment_sum": 0, "count": 0}
                entities[ent_id]["count"] += 1
                sentiment = meta.get("sentiment_score", 0)
                if isinstance(sentiment, (int, float)):
                    entities[ent_id]["sentiment_sum"] += sentiment * decay
                if nb:
                    entities[ent_id]["neighborhoods"].add(nb)

        # Business type nodes from licenses
        if source == "public_data":
            biz_type = meta.get("raw_record", {}).get("license_description", "")
            # Fallback: extract from content field
            if not biz_type:
                for line in content.split("\n"):
                    if line.startswith("license_description:"):
                        biz_type = line.split(":", 1)[1].strip()
                        break
            if biz_type and len(biz_type) > 2:
                bt_key = biz_type.strip().title()[:30]
                bt_id = f"biz:{bt_key.replace(' ', '-').lower()}"
                if bt_id not in business_types:
                    business_types[bt_id] = {"label": bt_key, "neighborhoods": {}}
                if nb:
                    business_types[bt_id]["neighborhoods"][nb] = business_types[bt_id]["neighborhoods"].get(nb, 0) + 1

    # Also scan raw docs for neighborhoods without enriched data
    for source_dir_name in ("news", "politics", "federal_register"):
        source_dir = get_raw_data_dir() / source_dir_name
        for f in iter_files(source_dir, pattern="*.json")[:100]:
            try:
                doc = load_json_file(f, default=None)
                if not isinstance(doc, dict):
                    continue
            except Exception:
                continue
            nb = doc.get("geo", {}).get("neighborhood", "")
            source = doc.get("source", source_dir_name)
            title = doc.get("title", "")
            content = doc.get("content", "")

            if not nb:
                nb = detect_neighborhood(f"{title} {content}")

            if source in ("politics", "federal_register") and title:
                reg_id = f"reg:{title[:50].replace(' ', '-').lower()}"
                if reg_id not in regulations:
                    regulations[reg_id] = {"label": title[:60], "neighborhoods": set(), "count": 0, "decay_sum": 0}
                regulations[reg_id]["count"] += 1
                if nb:
                    regulations[reg_id]["neighborhoods"].add(nb)

    # ── 3. Add entity/regulation/business_type nodes ──
    for reg_id, info in regulations.items():
        G.add_node(reg_id, type="regulation", label=info["label"], size=max(10, min(30, info["count"] * 3)))

    for ent_id, info in entities.items():
        if info["count"] >= 1:
            avg_sentiment = info["sentiment_sum"] / max(info["count"], 1)
            G.add_node(ent_id, type="entity", label=info["label"], sentiment=round(avg_sentiment, 2),
                       size=max(8, min(25, info["count"] * 2)))

    for bt_id, info in business_types.items():
        total = sum(info["neighborhoods"].values())
        if total >= 1:
            G.add_node(bt_id, type="business_type", label=info["label"], size=max(8, min(25, total)))

    # ── 4. Add edges ──
    # City-wide neighborhoods for regulations that don't mention a specific one
    city_wide_nbs = ["Loop", "Near North Side", "Lakeview", "Lincoln Park", "Hyde Park",
                     "Pilsen", "Logan Square", "Wicker Park", "Boystown", "Bronzeville"]

    for reg_id, info in regulations.items():
        if info["neighborhoods"]:
            for nb in info["neighborhoods"]:
                nb_id = f"nb:{nb}"
                if G.has_node(nb_id):
                    weight = round(min(1.0, info["decay_sum"] / 5), 2)
                    G.add_edge(reg_id, nb_id, type="regulates", weight=weight)
        else:
            # City-wide regulation — link to representative neighborhoods with low weight
            for nb in city_wide_nbs:
                nb_id = f"nb:{nb}"
                if G.has_node(nb_id):
                    weight = round(min(0.3, info["decay_sum"] / 10), 2)
                    G.add_edge(reg_id, nb_id, type="regulates", weight=max(0.05, weight))

    for ent_id, info in entities.items():
        if ent_id not in G:
            continue
        for nb in info["neighborhoods"]:
            nb_id = f"nb:{nb}"
            if G.has_node(nb_id):
                weight = round(min(1.0, abs(info["sentiment_sum"]) / max(info["count"], 1)), 2)
                G.add_edge(ent_id, nb_id, type="sentiment", weight=max(0.1, weight))

    for bt_id, info in business_types.items():
        if bt_id not in G:
            continue
        for nb, count in info["neighborhoods"].items():
            nb_id = f"nb:{nb}"
            if G.has_node(nb_id):
                weight = round(min(1.0, count / 10), 2)
                G.add_edge(bt_id, nb_id, type="competes_in", weight=max(0.1, weight))

    # ── 5. Serialize to JSON ──
    output: dict = {
        "nodes": [],
        "edges": [],
        "stats": {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "neighborhoods": len([n for n, d in G.nodes(data=True) if d.get("type") == "neighborhood"]),
            "regulations": len([n for n, d in G.nodes(data=True) if d.get("type") == "regulation"]),
            "entities": len([n for n, d in G.nodes(data=True) if d.get("type") == "entity"]),
            "business_types": len([n for n, d in G.nodes(data=True) if d.get("type") == "business_type"]),
            "built_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    for node_id, data in G.nodes(data=True):
        output["nodes"].append({"id": node_id, **{k: v for k, v in data.items()}})

    for u, v, data in G.edges(data=True):
        output["edges"].append({"source": u, "target": v, **{k: v2 for k, v2 in data.items()}})

    # Save to volume
    graph_path = get_processed_data_dir() / "graph" / "city_graph.json"
    write_json_file(graph_path, output, indent=None)
    volume.commit()

    print(f"City graph built: {output['stats']}")
    return output["stats"]
