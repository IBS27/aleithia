"""Neighborhood-focused routes and social synthesis endpoints."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from modal_app.api.services.cctv import aggregate_timeseries_for_neighborhood, load_cctv_for_neighborhood, load_parking_for_neighborhood
from modal_app.api.services.documents import (
    BUSINESS_TYPE_KEYWORDS,
    aggregate_demographics,
    compute_transit_score,
    filter_by_business_type,
    filter_by_neighborhood,
    filter_news_relevance,
    filter_politics_relevance,
    is_count_only_text,
    load_docs,
    sanitize_business_type,
    valid_neighborhood_names,
)
from modal_app.api.services.metrics import compute_metrics
from modal_app.api.services.tiktok import (
    TIKTOK_TARGET_COUNT,
    filter_tiktok_pool_for_profile,
    is_low_quality_tiktok_doc,
    maybe_spawn_tiktok_profile_refresh,
    normalize_tiktok_doc,
    parse_timestamp_epoch,
    parse_view_count,
    profile_tiktok_freshness,
    rank_tiktok_docs,
    spawn_reddit_fallback_persist,
)
from modal_app.common import CHICAGO_NEIGHBORHOODS, COMMUNITY_AREA_MAP
from modal_app.runtime import get_modal_function
from modal_app.volume import PROCESSED_DATA_PATH, RAW_DATA_PATH, volume
from modal_app.pipelines.reddit import (
    FALLBACK_BUDGET_MS,
    merge_rank_reddit_docs,
    rank_reddit_docs,
    reddit_docs_are_weak,
    search_reddit_fallback_runtime,
)

router = APIRouter()


@router.get("/brief/{neighborhood}")
async def brief(neighborhood: str, business_type: str = "Restaurant"):
    from modal_app.instrumentation import get_tracer, inject_context

    tracer = get_tracer("alethia.web")
    span_ctx = tracer.start_as_current_span("brief-request") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", f"{business_type} in {neighborhood}")
            span.set_attribute("brief.neighborhood", neighborhood)
            span.set_attribute("brief.business_type", business_type)

        neighborhood_intel_agent = get_modal_function("neighborhood_intel_agent")
        result = await neighborhood_intel_agent.remote.aio(
            neighborhood=neighborhood,
            business_type=business_type,
            trace_context=inject_context(),
        )

        if span:
            span.set_attribute("output.value", json.dumps({"data_points": result.get("data_points", 0)}))
        return result
    except Exception as exc:
        if span:
            span.set_attribute("error", str(exc))
        return {"error": str(exc), "neighborhood": neighborhood}
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


@router.get("/alerts")
async def alerts(business_type: str = "Restaurant"):
    del business_type

    alert_list = []
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    if enriched_dir.exists():
        for json_file in sorted(enriched_dir.rglob("*.json"), reverse=True)[:50]:
            try:
                doc = json.loads(json_file.read_text())
                sentiment = doc.get("sentiment", {})
                if sentiment.get("label") == "negative" and sentiment.get("score", 0) > 0.8:
                    alert_list.append(
                        {
                            "type": "negative_sentiment",
                            "title": doc.get("title", ""),
                            "source": doc.get("source", ""),
                            "neighborhood": doc.get("geo", {}).get("neighborhood", ""),
                            "severity": "high",
                        }
                    )
            except Exception:
                continue

    return {"alerts": alert_list[:20], "count": len(alert_list)}


@router.get("/neighborhood/{name}")
async def neighborhood(name: str, business_type: str = ""):
    from modal_app.instrumentation import get_tracer

    tracer = get_tracer("alethia.web")
    span_ctx = tracer.start_as_current_span("neighborhood-profile") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", name)
            span.set_attribute("neighborhood.name", name)

        if name.lower() not in valid_neighborhood_names():
            if span:
                span.set_attribute("error", f"Unknown neighborhood: {name}")
            return JSONResponse({"error": f"Unknown neighborhood: {name}"}, status_code=404)

        public_docs = load_docs("public_data", limit=500)
        nb_docs = filter_by_neighborhood(public_docs, name)
        inspections = []
        permits = []
        licenses = []
        for doc in nb_docs:
            dataset = doc.get("metadata", {}).get("dataset", "")
            if dataset == "food_inspections":
                inspections.append(doc)
            elif dataset == "building_permits":
                permits.append(doc)
            elif dataset == "business_licenses":
                licenses.append(doc)

        all_news = load_docs("news")
        all_politics = load_docs("politics")
        news_docs = filter_by_neighborhood(all_news, name)
        if news_docs:
            news_docs = filter_news_relevance(news_docs, business_type, name)
        politics_docs = filter_politics_relevance(filter_by_neighborhood(all_politics, name), business_type)

        all_reddit = load_docs("reddit")
        all_reviews = load_docs("reviews")
        all_realestate = load_docs("realestate")
        all_tiktok = [normalize_tiktok_doc(doc) for doc in load_docs("tiktok")]
        all_tiktok = [doc for doc in all_tiktok if not is_low_quality_tiktok_doc(doc)]
        all_tiktok_profile = filter_tiktok_pool_for_profile(all_tiktok, business_type)
        all_federal = load_docs("federal_register")

        reddit_docs = rank_reddit_docs(
            filter_by_neighborhood(all_reddit, name),
            business_type=business_type or "small business",
            neighborhood=name,
            min_score=0,
        )
        reviews_docs = filter_by_neighborhood(all_reviews, name)
        realestate_docs = filter_by_neighborhood(all_realestate, name)
        tiktok_docs = rank_tiktok_docs(all_tiktok_profile, business_type, name)
        federal_docs = filter_politics_relevance(filter_by_neighborhood(all_federal, name), business_type)
        profile_count, local_count, freshest_epoch = profile_tiktok_freshness(all_tiktok_profile, business_type, name)
        try:
            tiktok_refresh = await maybe_spawn_tiktok_profile_refresh(
                neighborhood=name,
                business_type=business_type or "small business",
                profile_count=profile_count,
                local_count=local_count,
                freshest_epoch=freshest_epoch,
            )
        except Exception as exc:
            print(f"tiktok_refresh_error: {exc}")
            tiktok_refresh = {
                "requested": False,
                "reason": f"refresh_error:{exc}",
                "cooldown_seconds_remaining": 0,
                "profile_docs": profile_count,
                "local_docs": local_count,
            }

        traffic_docs: list[dict] = []

        if business_type and reviews_docs:
            typed_reviews = filter_by_business_type(reviews_docs, business_type)
            if typed_reviews:
                reviews_docs = typed_reviews

        if reddit_docs_are_weak(
            reddit_docs,
            business_type=business_type or "small business",
            neighborhood=name,
            min_count=3,
            median_threshold=2.0,
        ):
            start_ms = int(time.time() * 1000)
            fallback_docs = await search_reddit_fallback_runtime(
                business_type=business_type or "small business",
                neighborhood=name,
                budget_ms=FALLBACK_BUDGET_MS,
            )
            latency_ms = int(time.time() * 1000) - start_ms
            print(
                "reddit_fallback_triggered",
                {
                    "neighborhood": name,
                    "business_type": business_type or "small business",
                    "fallback_latency_ms": latency_ms,
                    "fallback_docs_found": len(fallback_docs),
                    "adapter_used": (fallback_docs[0].get("metadata", {}) or {}).get("retrieval_method", "") if fallback_docs else "",
                },
            )
            if fallback_docs:
                await spawn_reddit_fallback_persist(fallback_docs)
                reddit_docs = merge_rank_reddit_docs(
                    reddit_docs,
                    fallback_docs,
                    business_type=business_type or "small business",
                    neighborhood=name,
                    min_score=0,
                )

        if not reddit_docs and all_reddit:
            reddit_docs = rank_reddit_docs(
                all_reddit,
                business_type=business_type or "small business",
                neighborhood=name,
                min_score=0,
            )[:10]

        if not reviews_docs and all_reviews:
            if business_type:
                typed = filter_by_business_type(all_reviews, business_type)
                reviews_docs = typed[:10] if typed else all_reviews[:5]
            else:
                reviews_docs = all_reviews[:5]

        if not realestate_docs and all_realestate:
            realestate_docs = all_realestate[:5]
        if not federal_docs and all_federal:
            federal_docs = filter_politics_relevance(all_federal, business_type)[:10]
        if not news_docs and all_news:
            news_docs = filter_news_relevance(all_news, business_type, name)[:10]
        if not politics_docs and all_politics:
            politics_docs = filter_politics_relevance(all_politics, business_type)[:10]

        failed = sum(1 for inspection in inspections if inspection.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))
        passed = sum(1 for inspection in inspections if inspection.get("metadata", {}).get("raw_record", {}).get("results") == "Pass")
        computed_metrics = compute_metrics(name, inspections, permits, licenses, news_docs, politics_docs, reviews_docs)
        demographics = aggregate_demographics(name)

        cctv_analysis = await load_cctv_for_neighborhood(name)
        if cctv_analysis.get("cameras"):
            cam_ids = [camera["camera_id"] for camera in cctv_analysis["cameras"]]
            ts = await aggregate_timeseries_for_neighborhood(name, camera_ids=cam_ids)
            if ts.get("hours"):
                cctv_analysis["peak_hour"] = ts["peak_hour"]
                cctv_analysis["peak_pedestrians"] = ts["peak_pedestrians"]

        transit_data = compute_transit_score(name)
        parking_data = load_parking_for_neighborhood(name)

        if span:
            span.set_attribute(
                "output.value",
                json.dumps({
                    "inspections": len(inspections),
                    "permits": len(permits),
                    "licenses": len(licenses),
                    "news": len(news_docs),
                }),
            )
            span.set_attribute("neighborhood.inspections", len(inspections))
            span.set_attribute("neighborhood.permits", len(permits))
            span.set_attribute("neighborhood.licenses", len(licenses))

        return {
            "neighborhood": name,
            "metrics": computed_metrics,
            "demographics": demographics,
            "inspections": inspections[:50],
            "permits": permits[:50],
            "licenses": licenses[:50],
            "news": news_docs[:20],
            "politics": politics_docs[:20],
            "federal_register": federal_docs[:20],
            "reddit": reddit_docs[:20],
            "reviews": reviews_docs[:20],
            "realestate": realestate_docs[:10],
            "tiktok": tiktok_docs[:TIKTOK_TARGET_COUNT],
            "tiktok_refresh": tiktok_refresh,
            "traffic": traffic_docs[:10],
            "cctv": cctv_analysis,
            "transit": transit_data,
            "parking": parking_data,
            "inspection_stats": {"total": len(inspections), "failed": failed, "passed": passed},
            "permit_count": len(permits),
            "license_count": len(licenses),
        }
    except Exception as exc:
        if span:
            span.set_attribute("error", str(exc))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


_SOCIAL_GENERIC_KEYWORDS = (
    "business",
    "small business",
    "owner",
    "opening",
    "closing",
    "foot traffic",
    "price",
    "customer",
    "rent",
    "construction",
    "permit",
    "license",
)


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _social_business_keywords(business_type: str) -> list[str]:
    bt = sanitize_business_type(business_type)
    if not bt:
        return list(_SOCIAL_GENERIC_KEYWORDS)
    keywords = BUSINESS_TYPE_KEYWORDS.get(bt, [bt])
    resolved = []
    for kw in keywords:
        clean = sanitize_business_type(kw)
        if clean:
            resolved.append(clean)
    return resolved or [bt]


def _extract_social_timestamp_epoch(doc: dict) -> float:
    ts = parse_timestamp_epoch(str(doc.get("timestamp", "") or ""))
    if ts > 0:
        return ts
    meta = doc.get("metadata", {}) or {}
    for key in ("created_at", "createdAt", "published_at", "scraped_at", "updated_at"):
        candidate = parse_timestamp_epoch(str(meta.get(key, "") or ""))
        if candidate > 0:
            return candidate
    for key in ("created_utc", "created"):
        raw = meta.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
        parsed = _coerce_float(raw, 0.0)
        if parsed > 0:
            return parsed
    return 0.0


def _social_doc_quality_score(doc: dict) -> float:
    title = str(doc.get("title", "") or "").strip()
    content = str(doc.get("content", "") or "").strip()
    score = 0.0
    if len(title) >= 12:
        score += 0.25
    if len(content) >= 80:
        score += 0.45
    elif len(content) >= 30:
        score += 0.25
    if any(sep in content for sep in (". ", "! ", "? ")):
        score += 0.2
    if not is_count_only_text(title):
        score += 0.1
    return min(1.0, score)


def _social_doc_engagement_score(doc: dict, source: str) -> float:
    meta = doc.get("metadata", {}) or {}
    if source == "reddit":
        score = max(0.0, _coerce_float(meta.get("score", 0)))
        comments = max(0.0, _coerce_float(meta.get("num_comments", 0)))
        upvote_ratio = _coerce_float(meta.get("upvote_ratio", 0.0))
        return min(1.0, (score / 200.0) + (comments / 80.0) + min(0.2, max(0.0, upvote_ratio - 0.5)))
    if source == "tiktok":
        views = int((meta.get("views_normalized") or 0) or 0)
        if views <= 0:
            views = parse_view_count(str(meta.get("views", "") or ""))
        likes = max(0.0, _coerce_float(meta.get("likes", 0)))
        comments = max(0.0, _coerce_float(meta.get("comments", 0)))
        return min(1.0, (views / 200_000.0) + (likes / 20_000.0) + (comments / 2_000.0))
    return 0.0


def _score_social_doc(doc: dict, business_type: str, neighborhood: str, source: str) -> float:
    keywords = _social_business_keywords(business_type)
    title = str(doc.get("title", "") or "")
    content = str(doc.get("content", "") or "")
    combined = f"{title} {content}".lower()

    business_hits = sum(1 for kw in keywords if kw and kw in combined)
    business_score = min(1.0, business_hits / 3.0)
    nb = (neighborhood or "").strip().lower()
    geo_nb = str((doc.get("geo", {}) or {}).get("neighborhood", "") or "").strip().lower()
    neighborhood_score = 1.0 if (nb and (nb in combined or geo_nb == nb)) else 0.0

    ts = _extract_social_timestamp_epoch(doc)
    if ts > 0:
        age_days = max(0.0, (time.time() - ts) / 86400.0)
        recency_score = max(0.0, 1.0 - (age_days / 21.0))
    else:
        recency_score = 0.25

    weighted = (
        0.38 * business_score
        + 0.22 * recency_score
        + 0.22 * _social_doc_engagement_score(doc, source)
        + 0.18 * _social_doc_quality_score(doc)
    )
    if neighborhood_score > 0:
        weighted = min(1.0, weighted + 0.1)
    return round(weighted, 5)


def _dedupe_social_docs(docs: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for doc in docs:
        doc_id = str(doc.get("id", "") or "").strip()
        if not doc_id:
            title = str(doc.get("title", "") or "").strip().lower()
            content = str(doc.get("content", "") or "").strip().lower()[:120]
            doc_id = f"fp:{title}|{content}"
        if doc_id in seen:
            continue
        seen.add(doc_id)
        deduped.append(doc)
    return deduped


def _rank_social_docs_deterministic(
    reddit_docs: list[dict],
    tiktok_docs: list[dict],
    business_type: str,
    neighborhood: str,
    max_total: int = 8,
) -> list[tuple[str, dict, float]]:
    def _rank_source(docs: list[dict], source: str) -> list[tuple[str, dict, float]]:
        ranked = []
        for doc in _dedupe_social_docs(docs):
            score = _score_social_doc(doc, business_type, neighborhood, source)
            ranked.append((source, doc, score))
        ranked.sort(
            key=lambda item: (item[2], _extract_social_timestamp_epoch(item[1]), str(item[1].get("id", "") or "")),
            reverse=True,
        )
        return ranked

    ranked_reddit = _rank_source(reddit_docs, "reddit")
    ranked_tiktok = _rank_source(tiktok_docs, "tiktok")
    merged: list[tuple[str, dict, float]] = []
    i_reddit = 0
    i_tiktok = 0
    primary = "reddit" if (ranked_reddit[0][2] if ranked_reddit else -1.0) >= (ranked_tiktok[0][2] if ranked_tiktok else -1.0) else "tiktok"
    secondary = "tiktok" if primary == "reddit" else "reddit"
    while len(merged) < max_total and (i_reddit < len(ranked_reddit) or i_tiktok < len(ranked_tiktok)):
        for source in (primary, secondary):
            if len(merged) >= max_total:
                break
            if source == "reddit" and i_reddit < len(ranked_reddit):
                merged.append(ranked_reddit[i_reddit])
                i_reddit += 1
            elif source == "tiktok" and i_tiktok < len(ranked_tiktok):
                merged.append(ranked_tiktok[i_tiktok])
                i_tiktok += 1
    return merged


def _trim_words(text: str, max_words: int) -> str:
    words = [word for word in re.split(r"\s+", text.strip()) if word]
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).strip(" -:;,")


def _deterministic_social_fallback_trends(
    ranked_docs: list[tuple[str, dict, float]],
    business_type: str,
    neighborhood: str,
    count: int = 3,
) -> list[dict]:
    if not ranked_docs:
        return []

    topic_rules = [
        ("Consumer Demand Signals", ("demand", "busy", "line", "crowd", "packed", "rush", "foot traffic", "weekend"), "Demand-related chatter appears elevated, suggesting stronger customer intent in this area."),
        ("Price Sensitivity Pattern", ("price", "cost", "expensive", "cheap", "deal", "budget", "value", "afford"), "Conversations frequently reference cost and value, indicating pricing strategy will strongly shape conversion."),
        ("Competition And Openings", ("opening", "new", "launch", "competitor", "another", "more", "restaurant", "cafe", "shop", "store"), "Multiple posts point to active business turnover and competitive movement in nearby corridors."),
        ("Operational Friction Risks", ("parking", "traffic", "construction", "permit", "license", "safety", "crime", "delay"), "Repeated mentions of logistics and compliance friction suggest execution risk that should be planned for upfront."),
    ]
    corpus = " ".join(
        f"{str(doc.get('title', '') or '')} {str(doc.get('content', '') or '')}".lower()
        for _, doc, _ in ranked_docs
    )
    avg_score = sum(score for _, _, score in ranked_docs) / max(1, len(ranked_docs))
    scored_topics: list[tuple[int, str, str]] = []
    for title, keywords, sentence in topic_rules:
        hits = sum(1 for kw in keywords if kw in corpus)
        if hits > 0:
            scored_topics.append((hits, title, sentence))
    scored_topics.sort(key=lambda item: item[0], reverse=True)

    trends: list[dict] = []
    biz_label = (business_type or "small businesses").strip()
    for _, title, sentence in scored_topics[:count]:
        detail = (
            f"{sentence} For {biz_label} in {neighborhood}, treat this as a directional signal and validate against permits, "
            "reviews, and local foot-traffic data before execution."
        )
        trends.append({"title": _trim_words(title, 8), "detail": detail})
    while len(trends) < count:
        confidence = "moderate" if avg_score >= 0.55 else "early-stage"
        detail = (
            f"Available social data indicates a {confidence} signal set for {biz_label} in {neighborhood}. "
            "Use this as input to planning, but confirm with broader neighborhood metrics."
        )
        trends.append({"title": "Market Signal Overview", "detail": detail})
    return trends[:count]


def _parse_social_trends_response(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                parsed = None
        if parsed is None:
            obj_match = re.search(r"\{.*\}", text, re.DOTALL)
            if obj_match:
                try:
                    parsed = json.loads(obj_match.group())
                except json.JSONDecodeError:
                    parsed = None

    if isinstance(parsed, dict):
        parsed = parsed.get("trends") or parsed.get("items") or parsed.get("insights") or parsed.get("data") or []
    if not isinstance(parsed, list):
        return []

    normalized = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = _trim_words(str(item.get("title") or item.get("name") or item.get("headline") or ""), 8)
        detail = str(item.get("detail") or item.get("description") or item.get("summary") or "").strip()
        if title and detail:
            normalized.append({"title": title, "detail": detail})
        if len(normalized) >= 3:
            break
    return normalized


@router.get("/social-trends/{neighborhood}")
async def social_trends(neighborhood: str, business_type: str = ""):
    from modal_app.instrumentation import get_tracer

    tracer = get_tracer("alethia.web")
    span_ctx = tracer.start_as_current_span("social-trends") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", neighborhood)
            span.set_attribute("social_trends.business_type", business_type or "general")

        volume.reload()
        if neighborhood.lower() not in valid_neighborhood_names():
            return JSONResponse({"error": f"Unknown neighborhood: {neighborhood}"}, status_code=404)

        all_reddit = load_docs("reddit")
        all_tiktok = [normalize_tiktok_doc(doc) for doc in load_docs("tiktok")]

        reddit_docs = rank_reddit_docs(
            filter_by_neighborhood(all_reddit, neighborhood),
            business_type=business_type or "small business",
            neighborhood=neighborhood,
            min_score=0,
        )
        if not reddit_docs and all_reddit:
            reddit_docs = rank_reddit_docs(
                all_reddit,
                business_type=business_type or "small business",
                neighborhood=neighborhood,
                min_score=0,
            )
        tiktok_docs = rank_tiktok_docs(all_tiktok, business_type or "small business", neighborhood)
        reddit_count = len(reddit_docs)
        tiktok_count = len(tiktok_docs)

        if span:
            span.set_attribute("social_trends.reddit_count", reddit_count)
            span.set_attribute("social_trends.tiktok_count", tiktok_count)

        if reddit_count == 0 and tiktok_count == 0:
            return {"neighborhood": neighborhood, "business_type": business_type, "trends": [], "source_counts": {"reddit": 0, "tiktok": 0}}

        reddit_snippets = [f"[Reddit] {doc.get('title', '')}: {doc.get('content', '')[:300]}" for doc in reddit_docs[:10]]
        tiktok_snippets = [
            f"[TikTok] {doc.get('title', '')} (views: {doc.get('metadata', {}).get('views', '')}): {doc.get('content', '')[:500]}"
            for doc in tiktok_docs[:5]
        ]
        all_snippets = "\n\n".join(reddit_snippets + tiktok_snippets)

        ranked_docs = _rank_social_docs_deterministic(
            reddit_docs=reddit_docs,
            tiktok_docs=tiktok_docs,
            business_type=business_type or "small business",
            neighborhood=neighborhood,
            max_total=15,
        )
        if not ranked_docs:
            ranked_docs = [("reddit", doc, 0.0) for doc in reddit_docs[:10]] + [("tiktok", doc, 0.0) for doc in tiktok_docs[:5]]

        system_prompt = (
            "You are a local market analyst. Given social media posts from a specific neighborhood, "
            "synthesize exactly 3 actionable insights tailored to someone opening or running a "
            f"{business_type or 'small business'} in {neighborhood}. "
            "Each insight should connect what locals are saying online to a concrete implication "
            "for that business type — e.g. unmet demand, competitive gaps, peak-hour patterns, or shifting customer preferences. "
            "Respond ONLY with a JSON object: {\"trends\": [ ... ]} containing 3 objects "
            "with `title` (max 8 words) and `detail` (1-2 sentences explaining the insight and why it matters for the business)."
        )
        user_prompt = f"Neighborhood: {neighborhood}\nBusiness type: {business_type or 'general'}\n\nSocial media content:\n{all_snippets}"

        from modal_app.openai_utils import build_chat_kwargs, get_openai_client, get_social_trends_model, openai_available

        msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        retry_used = False
        fallback_used = False
        if not openai_available():
            return JSONResponse(
                {"error": "Social trends synthesis unavailable: OpenAI not configured"},
                status_code=503,
            )

        try:
            client = get_openai_client()
            social_model = get_social_trends_model()
            create_kwargs = build_chat_kwargs(
                social_model,
                msgs,
                max_completion_tokens=512,
                gpt5_max_completion_tokens=2048,
                temperature=0.4,
                response_format={"type": "json_object"},
            )
            oai_resp = await client.chat.completions.create(**create_kwargs)
            raw = oai_resp.choices[0].message.content or ""
            choice = oai_resp.choices[0]
            finish = getattr(choice, "finish_reason", None)
            usage = getattr(oai_resp, "usage", None)
            print(f"[social-trends] model={social_model} finish_reason={finish} usage={usage} raw_preview={raw[:200]!r}")
        except Exception as exc:
            print(f"[social-trends] OpenAI call failed: {exc!r}")
            return JSONResponse(
                {"error": f"Social trends synthesis unavailable: OpenAI failed ({exc})"},
                status_code=503,
            )

        validated = _parse_social_trends_response(raw)
        if not validated:
            try:
                retry_used = True
                client = get_openai_client()
                social_model = get_social_trends_model()
                retry_msgs = [
                    {"role": "system", "content": "Return valid JSON only with shape {\"trends\":[{\"title\":\"...\",\"detail\":\"...\"}, ...]} and exactly 3 items. No markdown, no explanation."},
                    {"role": "user", "content": user_prompt},
                ]
                retry_kwargs = build_chat_kwargs(
                    social_model,
                    retry_msgs,
                    max_completion_tokens=512,
                    gpt5_max_completion_tokens=2048,
                    temperature=0.4,
                    response_format={"type": "json_object"},
                )
                retry_resp = await client.chat.completions.create(**retry_kwargs)
                retry_raw = retry_resp.choices[0].message.content or ""
                retry_choice = retry_resp.choices[0]
                retry_finish = getattr(retry_choice, "finish_reason", None)
                retry_usage = getattr(retry_resp, "usage", None)
                print(f"[social-trends] retry model={social_model} finish_reason={retry_finish} usage={retry_usage} raw_preview={retry_raw[:200]!r}")
                validated = _parse_social_trends_response(retry_raw)
            except Exception as exc:
                print(f"[social-trends] retry failed: {exc!r}")

        if len(validated) < 3:
            fallback_used = True
            fallback_trends = _deterministic_social_fallback_trends(
                ranked_docs=ranked_docs,
                business_type=business_type or "small business",
                neighborhood=neighborhood,
                count=3,
            )
            seen = {(item.get("title", ""), item.get("detail", "")) for item in validated}
            for trend in fallback_trends:
                key = (trend.get("title", ""), trend.get("detail", ""))
                if key in seen:
                    continue
                validated.append({"title": trend["title"], "detail": trend["detail"]})
                seen.add(key)
                if len(validated) >= 3:
                    break

        if len(validated) < 3:
            fallback_used = True
            biz_label = (business_type or "small businesses").strip()
            while len(validated) < 3:
                idx = len(validated) + 1
                title = "Market Signal Overview" if idx == 1 else f"Market Signal Overview {idx}"
                detail = (
                    f"Social activity is present for {biz_label} in {neighborhood}. "
                    "Use this as directional signal and validate against permits, reviews, and foot-traffic."
                )
                validated.append({"title": title, "detail": detail})

        validated = validated[:3]
        if span:
            span.set_attribute("social_trends.ranked_count", len(ranked_docs))
            span.set_attribute("social_trends.retry_used", retry_used)
            span.set_attribute("social_trends.fallback_used", fallback_used)
            span.set_attribute("social_trends.trend_count", len(validated))
        return {
            "neighborhood": neighborhood,
            "business_type": business_type,
            "trends": validated,
            "source_counts": {"reddit": reddit_count, "tiktok": tiktok_count},
        }
    except Exception as exc:
        if span:
            span.set_attribute("error", str(exc))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


@router.get("/trends/{neighborhood}")
async def get_trends(neighborhood: str):
    import hashlib

    volume.reload()
    baseline_path = Path(PROCESSED_DATA_PATH) / "trends" / "baselines" / f"{neighborhood}.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
    else:
        seed = int(hashlib.md5(neighborhood.encode()).hexdigest()[:8], 16)
        rng_base = (seed % 10) + 5
        baseline = {
            "hours": [
                {
                    "hour": hour,
                    "pedestrians": round(rng_base * (0.3 + 0.7 * abs(12 - abs(hour - 14)) / 12), 1),
                    "vehicles": round(rng_base * 1.8 * (0.2 + 0.8 * abs(12 - abs(hour - 13)) / 12), 1),
                    "congestion": round(0.1 + 0.5 * abs(12 - abs(hour - 14)) / 12, 2),
                }
                for hour in range(24)
            ]
        }

    hours = baseline["hours"]
    recent = hours[18:24]
    prior = hours[12:18]

    def avg_field(entries, field):
        vals = [entry[field] for entry in entries]
        return sum(vals) / len(vals) if vals else 0

    recent_peds = avg_field(recent, "pedestrians")
    prior_peds = avg_field(prior, "pedestrians")
    ped_change = round(((recent_peds - prior_peds) / max(prior_peds, 0.1)) * 100)
    recent_cong = avg_field(recent, "congestion")
    prior_cong = avg_field(prior, "congestion")
    cong_change = round(((recent_cong - prior_cong) / max(prior_cong, 0.01)) * 100)

    news_dir = Path(RAW_DATA_PATH) / "news"
    news_count = 0
    if news_dir.exists():
        for file_path in list(news_dir.rglob("*.json"))[:200]:
            try:
                doc = json.loads(file_path.read_text())
                geo = doc.get("geo", {})
                if geo.get("neighborhood", "").lower() == neighborhood.lower():
                    news_count += 1
            except Exception:
                continue
    news_trend = "up" if news_count > 5 else ("stable" if news_count > 2 else "down")

    anomalies = []
    traffic_dir = Path(RAW_DATA_PATH) / "traffic"
    if traffic_dir.exists():
        for date_dir in sorted(traffic_dir.iterdir(), reverse=True)[:1]:
            if not date_dir.is_dir():
                continue
            for file_path in date_dir.glob("*.json"):
                try:
                    doc = json.loads(file_path.read_text())
                    meta = doc.get("metadata", {})
                    if meta.get("is_anomaly") and doc.get("geo", {}).get("neighborhood", "").lower() == neighborhood.lower():
                        anomalies.append(
                            {
                                "type": meta.get("severity", "info"),
                                "description": meta.get("congestion_level", "anomaly detected"),
                                "road": doc.get("title", "Unknown road"),
                            }
                        )
                except Exception:
                    continue

    def trend_dir(change_pct):
        if change_pct > 5:
            return "up"
        if change_pct < -5:
            return "down"
        return "stable"

    return {
        "foot_traffic": {
            "trend": trend_dir(ped_change),
            "change_pct": ped_change,
            "current_avg": round(recent_peds, 1),
            "prior_avg": round(prior_peds, 1),
        },
        "congestion": {"trend": trend_dir(cong_change), "change_pct": cong_change, "anomalies": anomalies[:5]},
        "news_activity": {"trend": news_trend, "change_pct": (news_count - 3) * 10},
        "hours": hours,
    }
