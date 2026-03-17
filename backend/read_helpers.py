"""Pure document filtering and transformation helpers for backend routes."""

from __future__ import annotations

from typing import Iterable, Mapping


def filter_docs_by_neighborhood_match(
    docs: list[dict],
    neighborhood: str,
    *,
    geo_substring_fields: Iterable[str] = ("neighborhood", "community_area_name"),
    geo_exact_field_values: Mapping[str, object] | None = None,
    raw_record_fields: Iterable[str] = ("address", "community_area_name"),
    include_title: bool = True,
    include_content: bool = True,
    content_limit: int | None = None,
    min_content_match_length: int = 0,
) -> list[dict]:
    """Filter documents by neighborhood while allowing caller-specific matching knobs."""
    if not neighborhood:
        return docs

    needle = neighborhood.lower()
    geo_exact_field_values = geo_exact_field_values or {}
    results = []
    for doc in docs:
        geo = doc.get("geo", {})
        matched = any(needle in str(geo.get(field) or "").lower() for field in geo_substring_fields)

        if not matched:
            for field, expected in geo_exact_field_values.items():
                actual = geo.get(field)
                if isinstance(expected, str):
                    if str(actual or "").lower() == expected.lower():
                        matched = True
                        break
                elif actual == expected:
                    matched = True
                    break

        if not matched and include_title:
            matched = needle in str(doc.get("title") or "").lower()

        if not matched and include_content and len(needle) >= min_content_match_length:
            content = str(doc.get("content") or "").lower()
            if content_limit is not None:
                content = content[:content_limit]
            matched = needle in content

        if not matched and raw_record_fields:
            raw = doc.get("metadata", {}).get("raw_record", {})
            matched = any(needle in str(raw.get(field) or "").lower() for field in raw_record_fields)

        if matched:
            results.append(doc)
    return results


def filter_docs_by_neighborhood(docs: list[dict], neighborhood: str) -> list[dict]:
    """Filter documents that match a neighborhood using existing backend heuristics."""
    return filter_docs_by_neighborhood_match(
        docs,
        neighborhood,
        geo_substring_fields=("neighborhood", "community_area_name"),
        raw_record_fields=("address", "community_area_name"),
        include_title=True,
        include_content=True,
    )


def filter_public_data_by_dataset(docs: list[dict], dataset: str) -> list[dict]:
    """Filter public_data docs by dataset type (for example food_inspections)."""
    return [doc for doc in docs if doc.get("metadata", {}).get("dataset") == dataset]


def transform_doc_for_graph(doc: dict) -> dict:
    """Normalize document payloads for graph responses while preserving current fields."""
    memories = doc.get("memories", doc.get("memoryEntries", []))
    memory_entries = []
    for memory in memories:
        rels = memory.get("memoryRelations")
        if isinstance(rels, dict):
            rels = [
                {"targetMemoryId": key, "relationType": value}
                for key, value in rels.items()
                if value in ("updates", "extends", "derives")
            ]
        entry = {
            "id": memory.get("id", ""),
            "documentId": doc.get("id", ""),
            "content": memory.get("memory", memory.get("content")),
            "summary": memory.get("summary"),
            "title": memory.get("title"),
            "createdAt": memory.get("createdAt", memory.get("created_at")),
            "updatedAt": memory.get("updatedAt", memory.get("updated_at")),
            "isLatest": memory.get("isLatest", True),
            "isForgotten": memory.get("isForgotten"),
            "forgetAfter": memory.get("forgetAfter"),
            "relation": memory.get("relation") or memory.get("changeType"),
            "memoryRelations": rels if isinstance(rels, list) else memory.get("memoryRelations"),
            "updatesMemoryId": memory.get("updatesMemoryId"),
            "nextVersionId": memory.get("nextVersionId"),
            "parentMemoryId": memory.get("parentMemoryId"),
            "rootMemoryId": memory.get("rootMemoryId"),
            "metadata": memory.get("metadata"),
            "spaceId": memory.get("spaceId"),
            "spaceContainerTag": memory.get("spaceContainerTag"),
        }
        memory_entries.append(entry)

    out = {
        "id": doc.get("id", ""),
        "customId": doc.get("customId"),
        "title": doc.get("title"),
        "content": doc.get("content"),
        "summary": doc.get("summary"),
        "url": doc.get("url"),
        "source": doc.get("source"),
        "type": doc.get("type", doc.get("documentType")),
        "status": doc.get("status", "done"),
        "metadata": doc.get("metadata"),
        "createdAt": doc.get("createdAt", doc.get("created_at")),
        "updatedAt": doc.get("updatedAt", doc.get("updated_at")),
        "memoryEntries": memory_entries,
    }
    if doc.get("x") is not None:
        out["x"] = doc["x"]
    if doc.get("y") is not None:
        out["y"] = doc["y"]
    if doc.get("summaryEmbedding") is not None:
        out["summaryEmbedding"] = doc["summaryEmbedding"]
    return out
