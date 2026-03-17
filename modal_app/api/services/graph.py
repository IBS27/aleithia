"""Graph helpers for Modal API routes."""
from __future__ import annotations

import copy
from pathlib import Path

from backend.read_helpers import transform_doc_for_graph
from backend.shared_data import load_first_matching_json, load_json_file
from modal_app.api.cache import cache
from modal_app.api.services.documents import load_docs
from modal_app.common import CHICAGO_NEIGHBORHOODS, NEIGHBORHOOD_CENTROIDS, detect_neighborhood
from modal_app.volume import PROCESSED_DATA_PATH, volume


def build_city_graph_fallback() -> dict:
    nodes = []
    for neighborhood in CHICAGO_NEIGHBORHOODS:
        centroid = NEIGHBORHOOD_CENTROIDS.get(neighborhood)
        if centroid:
            lat, lng = centroid
            nodes.append({"id": f"nb:{neighborhood}", "type": "neighborhood", "label": neighborhood, "lat": lat, "lng": lng, "size": 40})
        else:
            nodes.append({"id": f"nb:{neighborhood}", "type": "neighborhood", "label": neighborhood, "size": 40})

    edges = []
    public_docs = load_docs("public_data", limit=500)
    nb_pairs: set[tuple[str, str]] = set()
    for doc in public_docs:
        meta = doc.get("metadata", {})
        geo = meta.get("geo", {})
        nb = (geo.get("neighborhood") or "").strip()
        if not nb or nb not in CHICAGO_NEIGHBORHOODS:
            nb = detect_neighborhood(doc.get("content", "") or doc.get("title", ""))
        if nb:
            dataset = meta.get("dataset", "")
            for other in public_docs[:100]:
                other_meta = other.get("metadata", {})
                other_geo = other_meta.get("geo", {})
                other_nb = (other_geo.get("neighborhood") or "").strip()
                if not other_nb:
                    other_nb = detect_neighborhood(other.get("content", "") or other.get("title", ""))
                if other_nb and other_nb != nb and other_meta.get("dataset") == dataset:
                    nb_pairs.add(tuple(sorted([nb, other_nb])))

    for a, b in list(nb_pairs)[:400]:
        edges.append({"source": f"nb:{a}", "target": f"nb:{b}", "weight": 1})
    return {"nodes": nodes, "edges": edges}


async def load_full_graph() -> dict:
    await volume.reload.aio()
    candidate_paths = [
        Path(PROCESSED_DATA_PATH) / "city_graph.json",
        Path(PROCESSED_DATA_PATH) / "graph" / "city_graph.json",
        Path(PROCESSED_DATA_PATH) / "graph.json",
    ]
    existing = next((path for path in candidate_paths if path.exists()), None)
    if not existing:
        return build_city_graph_fallback()

    cache_key = f"graph:full:{int(existing.stat().st_mtime)}"

    def _loader() -> dict:
        data = load_first_matching_json(
            candidate_paths,
            predicate=lambda payload: isinstance(payload, dict) and payload.get("nodes") is not None,
            default=None,
        )
        if data is not None:
            return data
        return build_city_graph_fallback()

    return copy.deepcopy(cache.get_or_set(cache_key, 10.0, _loader))


def load_city_graph() -> dict:
    volume.reload()
    graph_path = Path(PROCESSED_DATA_PATH) / "graph" / "city_graph.json"
    if not graph_path.exists():
        return {"nodes": [], "edges": [], "stats": {}}

    cache_key = f"graph:city:{int(graph_path.stat().st_mtime)}"

    def _loader() -> dict:
        return load_json_file(graph_path, default={"nodes": [], "edges": [], "stats": {}})

    return copy.deepcopy(cache.get_or_set(cache_key, 10.0, _loader))
