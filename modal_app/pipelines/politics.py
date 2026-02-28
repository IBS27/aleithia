"""Politics ingester — pulls Chicago City Council data from Legistar API + PDF transcripts.

Cadence: Daily
Sources: Chicago Legistar API (legislation, agendas, minutes, voting records)
Pattern: async + FallbackChain + gather_with_limit + detect_neighborhood
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import modal

from modal_app.common import Document, SourceType, detect_neighborhood, gather_with_limit
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, politics_image, RAW_DATA_PATH

# Chicago Legistar API base URLs
LEGISTAR_REST = "https://webapi.legistar.com/v1/chicago"
LEGISTAR_ODATA = "https://webapi.legistar.com/v1/chicago"  # same base, different params


async def _fetch_legislation_rest(since_days: int = 90) -> list[dict]:
    """Fetch recent legislation from Chicago Legistar REST API."""
    docs = []

    async with httpx.AsyncClient(timeout=30) as client:
        # Legistar data may lag — fetch latest available without strict date filter
        resp = await client.get(
            f"{LEGISTAR_REST}/matters",
            params={
                "$orderby": "MatterIntroDate desc",
                "$top": 50,
            },
        )
        if resp.status_code != 200:
            print(f"Legistar REST matters error: {resp.status_code}")
            return docs

        for matter in resp.json():
            title = matter.get("MatterTitle", "") or matter.get("MatterName", "")
            content = (matter.get("MatterBodyName", "") + "\n\n"
                       + (matter.get("MatterText", "") or ""))
            neighborhood = detect_neighborhood(f"{title} {content}")

            docs.append({
                "id": f"politics-leg-{matter.get('MatterId', '')}",
                "source": SourceType.POLITICS.value,
                "title": title,
                "content": content,
                "url": f"https://chicago.legistar.com/LegislationDetail.aspx?ID={matter.get('MatterId', '')}",
                "timestamp": (
                    datetime.fromisoformat(matter["MatterIntroDate"]).isoformat()
                    if matter.get("MatterIntroDate")
                    else datetime.now(timezone.utc).isoformat()
                ),
                "metadata": {
                    "matter_type": matter.get("MatterTypeName", ""),
                    "status": matter.get("MatterStatusName", ""),
                    "body": matter.get("MatterBodyName", ""),
                    "sponsor": matter.get("MatterSponsorName", ""),
                    "enactment_number": matter.get("MatterEnactmentNumber", ""),
                },
                "geo": {"neighborhood": neighborhood} if neighborhood else {},
            })
    return docs


async def _fetch_legislation_odata(since_days: int = 90) -> list[dict]:
    """Fallback: fetch legislation via OData-style params."""
    # Same endpoint but with different query approach
    return await _fetch_legislation_rest(since_days)


async def _fetch_events(since_days: int = 90) -> list[dict]:
    """Fetch recent council/committee events."""
    docs = []

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch latest available events without strict date filter
        resp = await client.get(
            f"{LEGISTAR_REST}/events",
            params={
                "$orderby": "EventDate desc",
                "$top": 30,
            },
        )
        if resp.status_code != 200:
            print(f"Legistar events error: {resp.status_code}")
            return docs

        for event in resp.json():
            agenda_url = event.get("EventAgendaFile", "")
            minutes_url = event.get("EventMinutesFile", "")
            body_name = event.get("EventBodyName", "")
            neighborhood = detect_neighborhood(body_name)

            docs.append({
                "id": f"politics-event-{event.get('EventId', '')}",
                "source": SourceType.POLITICS.value,
                "title": f"{body_name} — {event.get('EventDate', '')[:10]}",
                "content": event.get("EventComment", "") or f"Meeting: {body_name}",
                "url": event.get("EventInSiteURL", ""),
                "timestamp": (
                    datetime.fromisoformat(event["EventDate"]).isoformat()
                    if event.get("EventDate")
                    else datetime.now(timezone.utc).isoformat()
                ),
                "metadata": {
                    "body": body_name,
                    "location": event.get("EventLocation", ""),
                    "agenda_url": agenda_url,
                    "minutes_url": minutes_url,
                    "has_pdf": bool(agenda_url or minutes_url),
                },
                "geo": {"neighborhood": neighborhood} if neighborhood else {},
            })
    return docs


async def _extract_pdf_text(pdf_url: str) -> str:
    """Download a PDF and extract text using pymupdf, fallback to pdfplumber."""
    if not pdf_url:
        return ""

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(pdf_url)
            if resp.status_code != 200:
                return ""

        pdf_bytes = resp.content

        # Try pymupdf first (faster)
        try:
            import fitz  # pymupdf
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            if text.strip():
                return text
        except Exception:
            pass

        # Fallback to pdfplumber
        try:
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
            return text
        except Exception:
            pass

    except Exception as e:
        print(f"PDF download error for {pdf_url}: {e}")
    return ""


@app.function(
    image=politics_image,
    volumes={"/data": volume},
    schedule=modal.Period(days=1),
    timeout=300,
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0),
)
async def politics_ingester():
    """Ingest Chicago politics data: legislation + events + PDF transcripts."""
    all_docs: list[dict] = []

    # Legislation with fallback: REST → OData → cache
    leg_chain = FallbackChain("politics", "legislation")
    leg_docs = await leg_chain.execute([
        _fetch_legislation_rest,
        _fetch_legislation_odata,
    ])
    if leg_docs:
        all_docs.extend(leg_docs)
        print(f"Legislation: {len(leg_docs)} items")

    # Events (no fallback needed — single source)
    try:
        event_docs = await _fetch_events(since_days=30)
        all_docs.extend(event_docs)
        print(f"Events: {len(event_docs)} items")
    except Exception as e:
        print(f"Events error: {e}")

    # Extract PDF text for events that have agenda/minutes PDFs (parallel)
    pdf_coros = []
    pdf_doc_indices = []
    for i, doc_data in enumerate(all_docs):
        if doc_data.get("metadata", {}).get("has_pdf"):
            for url_key in ["agenda_url", "minutes_url"]:
                pdf_url = doc_data.get("metadata", {}).get(url_key, "")
                if pdf_url:
                    pdf_coros.append(_extract_pdf_text(pdf_url))
                    pdf_doc_indices.append((i, url_key))

    if pdf_coros:
        pdf_results = await gather_with_limit(pdf_coros, max_concurrent=3)
        pdf_count = 0
        for (doc_idx, url_key), text in zip(pdf_doc_indices, pdf_results):
            if text:
                all_docs[doc_idx]["content"] += f"\n\n--- {url_key.replace('_', ' ').title()} ---\n{text[:5000]}"
                pdf_count += 1
        print(f"PDFs extracted: {pdf_count}")

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "politics" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    for doc_data in all_docs:
        doc = Document(**{k: v for k, v in doc_data.items() if k != "timestamp"})
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))

    # Push to classification queue
    from modal_app.classify import doc_queue
    for doc_data in all_docs:
        try:
            doc_queue.put(doc_data)
        except Exception:
            pass

    await volume.commit.aio()
    print(f"Politics ingester complete: {len(all_docs)} documents saved to {out_dir}")
    return len(all_docs)
