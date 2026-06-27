from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient


def _public_doc(doc_id: str, dataset: str, *, lat: object = "", lng: object = "", raw: dict | None = None, geo: dict | None = None) -> dict:
    return {
        "id": doc_id,
        "source": "public_data",
        "title": f"{dataset} record",
        "content": "",
        "metadata": {
            "dataset": dataset,
            "raw_record": raw or {},
        },
        "geo": geo if geo is not None else {"lat": lat, "lng": lng, "neighborhood": "", "community_area": ""},
    }


def test_neighborhood_volume_reload_is_bounded(monkeypatch) -> None:
    from modal_app.api.routes import neighborhoods as neighborhood_routes

    class SlowReload:
        async def aio(self) -> None:
            await asyncio.sleep(1)

    class SlowVolume:
        reload = SlowReload()

    monkeypatch.setenv("ALEITHIA_SHARED_DATA_BACKEND", "modal")
    monkeypatch.setenv("ALEITHIA_MODAL_VOLUME_RELOAD_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(neighborhood_routes, "volume", SlowVolume())

    started = time.monotonic()
    asyncio.run(neighborhood_routes._reload_volume_if_needed("test"))

    assert time.monotonic() - started < 0.5


def test_modal_neighborhood_profile_uses_actual_source_matches(monkeypatch) -> None:
    from modal_app.api.routes import neighborhoods as neighborhood_routes
    from modal_app.web import web_app

    public_by_dataset = {
        "food_inspections": [
            _public_doc(
                "inspection-loop",
                "food_inspections",
                lat="41.88197704758362",
                lng="-87.63887583987513",
                raw={"results": "Fail"},
            ),
            _public_doc(
                "inspection-far",
                "food_inspections",
                lat="41.736782316890434",
                lng="-87.58712604619033",
                raw={"results": "Pass"},
            ),
        ],
        "building_permits": [
            _public_doc(
                "permit-loop",
                "building_permits",
                raw={"permit_type": "PERMIT - NEW CONSTRUCTION", "community_area": "32"},
                geo={"community_area": "32"},
            )
        ],
        "business_licenses": [
            _public_doc(
                "license-loop",
                "business_licenses",
                raw={"doing_business_as_name": "LOOP COFFEE", "license_description": "Coffee Shop", "community_area": "32"},
                geo={},
            )
        ],
    }

    docs_by_source = {
        "news": [
            {"id": "news-loop", "title": "Loop storefront demand rises", "content": "Coffee shops report commuter demand.", "geo": {"neighborhood": "Loop"}, "metadata": {}},
            {"id": "news-other", "title": "Rogers Park item", "content": "", "geo": {"neighborhood": "Rogers Park"}, "metadata": {}},
        ],
        "politics": [
            {"id": "policy-loop", "title": "Loop zoning update", "content": "", "geo": {"neighborhood": "Loop"}, "metadata": {"matter_type": "Ordinance"}},
        ],
        "reddit": [
            {"id": "reddit-loop", "title": "Loop coffee demand", "content": "Workers want more espresso options.", "geo": {"neighborhood": "Loop"}, "metadata": {"score": 10, "num_comments": 2}},
        ],
        "reviews": [
            {"id": "review-loop", "title": "Loop cafe", "content": "Rating: 4.6/5.", "geo": {}, "metadata": {"neighborhood": "Loop", "rating": 4.6, "categories": ["Coffee"]}},
            {"id": "review-west-loop", "title": "West Loop cafe", "content": "Rating: 4.4/5.", "geo": {"neighborhood": "West Loop"}, "metadata": {"rating": 4.4, "categories": ["Coffee"]}},
        ],
        "realestate": [
            {"id": "listing-loop", "title": "Loop retail lease", "content": "Retail space in the Loop.", "geo": {"neighborhood": "Loop"}, "metadata": {"listing_type": "lease", "price": "$4,000/mo"}},
            {"id": "listing-placeholder", "title": "Demo listing", "content": "Placeholder", "geo": {"neighborhood": "Loop"}, "metadata": {"is_placeholder": True}},
            {"id": "listing-west-loop", "title": "West Loop retail lease", "content": "Retail space in West Loop.", "geo": {"neighborhood": "West Loop"}, "metadata": {"listing_type": "lease"}},
        ],
        "tiktok": [
            {
                "id": "tiktok-loop",
                "title": "TikTok video",
                "content": "12K\n[Transcript] Loop coffee shops are busy after work.",
                "url": "https://www.tiktok.com/@loopcoffee/video/123",
                "geo": {},
                "metadata": {"query_scope": "local", "query_neighborhood": "Loop", "views": "12K"},
            }
        ],
        "federal_register": [
            {
                "id": "fed-2026-08108",
                "title": "Food permit compliance guidance",
                "content": "Food permit and inspection guidance for restaurants.",
                "geo": {"neighborhood": "Loop"},
                "metadata": {"agency": "FDA"},
            },
            {
                "id": "fed-2026-08108",
                "title": "Food permit compliance guidance",
                "content": "Duplicate copy from cached federal data.",
                "geo": {"neighborhood": "Loop"},
                "metadata": {"agency": "FDA"},
            },
        ],
    }

    monkeypatch.setattr(
        neighborhood_routes,
        "load_live_public_dataset_docs",
        lambda dataset, neighborhood, limit=200: public_by_dataset.get(dataset, []),
    )
    monkeypatch.setattr(
        neighborhood_routes,
        "load_public_dataset_docs_for_neighborhood",
        lambda dataset, neighborhood, limit=200: public_by_dataset.get(dataset, []),
    )
    monkeypatch.setattr(neighborhood_routes, "load_public_dataset_docs", lambda dataset, limit=200: public_by_dataset.get(dataset, []))
    monkeypatch.setattr(neighborhood_routes, "load_docs", lambda source, limit=200: docs_by_source.get(source, []))
    monkeypatch.setattr(neighborhood_routes, "compute_transit_score", lambda name: {"stations_nearby": 4, "total_daily_riders": 21000, "transit_score": 100, "station_names": ["Clark/Lake", "Washington/Wabash"]})
    monkeypatch.setattr(neighborhood_routes, "load_parking_for_neighborhood", lambda name: None)

    async def fake_load_cctv_for_neighborhood(name: str) -> dict:
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    async def fake_aggregate_timeseries_for_neighborhood(name: str, camera_ids=None) -> dict:
        return {}

    monkeypatch.setattr(neighborhood_routes, "load_cctv_for_neighborhood", fake_load_cctv_for_neighborhood)
    monkeypatch.setattr(neighborhood_routes, "aggregate_timeseries_for_neighborhood", fake_aggregate_timeseries_for_neighborhood)

    payload = TestClient(web_app).get("/neighborhood/Loop?business_type=Coffee%20Shop").json()

    assert [doc["id"] for doc in payload["inspections"]] == ["inspection-loop"]
    assert payload["inspection_stats"] == {"total": 1, "failed": 1, "passed": 0}
    assert [doc["id"] for doc in payload["permits"]] == ["permit-loop"]
    assert [doc["id"] for doc in payload["licenses"]] == ["license-loop"]
    assert [doc["id"] for doc in payload["news"]] == ["news-loop"]
    assert [doc["id"] for doc in payload["reviews"]] == ["review-loop"]
    assert [doc["id"] for doc in payload["realestate"]] == ["listing-loop"]
    assert [doc["id"] for doc in payload["tiktok"]] == ["tiktok-loop"]
    assert [doc["id"] for doc in payload["federal_register"]] == ["fed-2026-08108"]
    assert payload["tiktok_refresh"]["reason"] == "profile_route_read_only"
    assert payload["transit"]["stations_nearby"] == 4


def test_modal_neighborhood_profile_uses_wider_citywide_source_windows(monkeypatch) -> None:
    from modal_app.api.routes import neighborhoods as neighborhood_routes
    from modal_app.web import web_app

    observed_limits: dict[str, int] = {}

    def fake_load_docs(source: str, limit: int = 200) -> list[dict]:
        observed_limits[source] = limit
        if source == "reviews":
            docs = [
                {
                    "id": "review-other",
                    "title": "Logan Square cafe",
                    "content": "Rating: 4.5/5.",
                    "geo": {"neighborhood": "Logan Square"},
                    "metadata": {"rating": 4.5, "categories": ["Coffee"]},
                }
            ]
            if limit > 32:
                docs.append(
                    {
                        "id": "review-loop",
                        "title": "Loop cafe",
                        "content": "Rating: 4.6/5.",
                        "geo": {},
                        "metadata": {"neighborhood": "Loop", "rating": 4.6, "categories": ["Coffee"]},
                    }
                )
            return docs
        if source == "realestate":
            docs = [
                {
                    "id": "listing-placeholder",
                    "title": "Demo listing",
                    "content": "Placeholder",
                    "geo": {"neighborhood": "Loop"},
                    "metadata": {"is_placeholder": True},
                }
            ]
            if limit > 32:
                docs.append(
                    {
                        "id": "listing-loop",
                        "title": "Loop retail lease",
                        "content": "Retail space in the Loop.",
                        "geo": {"neighborhood": "Loop"},
                        "metadata": {"listing_type": "lease", "price": "$4,000/mo"},
                    }
                )
            return docs
        if source == "reddit":
            return [
                {
                    "id": "reddit-loop",
                    "title": "Coffee demand in Loop",
                    "content": "Office workers want faster coffee options.",
                    "geo": {"neighborhood": "Loop"},
                    "metadata": {"score": 12, "num_comments": 4},
                }
            ] if limit > 32 else []
        return []

    async def fake_public_dataset_loader(dataset: str, limit: int = 200, *, neighborhood: str | None = None) -> list[dict]:
        del dataset, limit, neighborhood
        return []

    monkeypatch.setattr(neighborhood_routes, "_load_public_dataset_docs_bounded", fake_public_dataset_loader)
    monkeypatch.setattr(neighborhood_routes, "load_docs", fake_load_docs)
    monkeypatch.setattr(neighborhood_routes, "compute_transit_score", lambda name: {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []})
    monkeypatch.setattr(neighborhood_routes, "load_parking_for_neighborhood", lambda name: None)

    async def fake_load_cctv_for_neighborhood(name: str) -> dict:
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    async def fake_aggregate_timeseries_for_neighborhood(name: str, camera_ids=None) -> dict:
        return {}

    monkeypatch.setattr(neighborhood_routes, "load_cctv_for_neighborhood", fake_load_cctv_for_neighborhood)
    monkeypatch.setattr(neighborhood_routes, "aggregate_timeseries_for_neighborhood", fake_aggregate_timeseries_for_neighborhood)

    payload = TestClient(web_app).get("/neighborhood/Loop?business_type=Coffee%20Shop").json()

    assert observed_limits["reviews"] > 32
    assert observed_limits["realestate"] > 32
    assert observed_limits["reddit"] > 32
    assert observed_limits["news"] > 32
    assert observed_limits["politics"] > 32
    assert observed_limits["federal_register"] > 32
    assert [doc["id"] for doc in payload["reviews"]] == ["review-loop"]
    assert [doc["id"] for doc in payload["realestate"]] == ["listing-loop"]
    assert [doc["id"] for doc in payload["reddit"]] == ["reddit-loop"]


def test_modal_neighborhood_profile_fetches_live_reviews_when_cache_has_no_match(monkeypatch) -> None:
    from modal_app.api.routes import neighborhoods as neighborhood_routes
    from modal_app.web import web_app

    async def fake_public_dataset_loader(dataset: str, limit: int = 200, *, neighborhood: str | None = None) -> list[dict]:
        del dataset, limit, neighborhood
        return []

    def fake_load_docs(source: str, limit: int = 200) -> list[dict]:
        del source, limit
        return []

    def fake_live_reviews(neighborhood: str, business_type: str = "", limit: int = 12) -> list[dict]:
        assert neighborhood == "Loop"
        assert business_type == "Coffee Shop"
        assert limit == 12
        return [
            {
                "id": "gplaces-live-loop-cafe",
                "title": "Loop Cafe",
                "content": "Loop Cafe — Rating: 4.7/5 (120 reviews).",
                "geo": {"neighborhood": "Loop"},
                "metadata": {"rating": 4.7, "review_count": 120, "categories": ["Coffee"]},
            }
        ]

    monkeypatch.setattr(neighborhood_routes, "_load_public_dataset_docs_bounded", fake_public_dataset_loader)
    monkeypatch.setattr(neighborhood_routes, "load_docs", fake_load_docs)
    monkeypatch.setattr(neighborhood_routes, "load_live_review_docs", fake_live_reviews)
    monkeypatch.setattr(neighborhood_routes, "compute_transit_score", lambda name: {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []})
    monkeypatch.setattr(neighborhood_routes, "load_parking_for_neighborhood", lambda name: None)

    async def fake_load_cctv_for_neighborhood(name: str) -> dict:
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    async def fake_aggregate_timeseries_for_neighborhood(name: str, camera_ids=None) -> dict:
        return {}

    monkeypatch.setattr(neighborhood_routes, "load_cctv_for_neighborhood", fake_load_cctv_for_neighborhood)
    monkeypatch.setattr(neighborhood_routes, "aggregate_timeseries_for_neighborhood", fake_aggregate_timeseries_for_neighborhood)

    payload = TestClient(web_app).get("/neighborhood/Loop?business_type=Coffee%20Shop").json()

    assert [doc["id"] for doc in payload["reviews"]] == ["gplaces-live-loop-cafe"]


def test_modal_neighborhood_public_dataset_falls_back_to_cached_docs(monkeypatch) -> None:
    import asyncio

    from modal_app.api.routes import neighborhoods as neighborhood_routes

    cached_docs = [
        _public_doc(
            "inspection-loop-cached",
            "food_inspections",
            raw={"results": "Pass"},
            geo={"neighborhood": "Loop"},
        )
    ]
    observed: dict[str, int] = {}

    def fail_live_fetch(dataset: str, neighborhood: str, limit: int = 200) -> list[dict]:
        del dataset, neighborhood, limit
        raise RuntimeError("socrata unavailable")

    def cached_fetch(dataset: str, limit: int = 200) -> list[dict]:
        observed["limit"] = limit
        return cached_docs if dataset == "food_inspections" else []

    monkeypatch.setattr(neighborhood_routes, "load_public_dataset_docs_for_neighborhood", lambda *args, **kwargs: [])
    monkeypatch.setattr(neighborhood_routes, "load_live_public_dataset_docs", fail_live_fetch)
    monkeypatch.setattr(neighborhood_routes, "load_public_dataset_docs", cached_fetch)

    docs = asyncio.run(
        neighborhood_routes._load_public_dataset_docs_bounded(
            "food_inspections",
            120,
            neighborhood="Loop",
        )
    )

    assert [doc["id"] for doc in docs] == ["inspection-loop-cached"]
    assert observed["limit"] == 120


def test_modal_neighborhood_public_dataset_uses_index_before_raw_cache(monkeypatch) -> None:
    import asyncio

    from modal_app.api.routes import neighborhoods as neighborhood_routes

    indexed_docs = [
        _public_doc(
            "permit-loop-indexed",
            "building_permits",
            raw={"permit_type": "RENOVATION"},
            geo={"neighborhood": "Loop"},
        )
    ]

    def fail_live_fetch(dataset: str, neighborhood: str, limit: int = 200) -> list[dict]:
        del dataset, neighborhood, limit
        raise RuntimeError("socrata unavailable")

    def indexed_fetch(dataset: str, neighborhood: str, limit: int = 200) -> list[dict]:
        assert dataset == "building_permits"
        assert neighborhood == "Loop"
        assert limit == 120
        return indexed_docs

    def raw_cache_should_not_run(dataset: str, limit: int = 200) -> list[dict]:
        raise AssertionError(f"raw cache should not run for {dataset}:{limit}")

    monkeypatch.setattr(neighborhood_routes, "load_live_public_dataset_docs", fail_live_fetch)
    monkeypatch.setattr(neighborhood_routes, "load_public_dataset_docs_for_neighborhood", indexed_fetch)
    monkeypatch.setattr(neighborhood_routes, "load_public_dataset_docs", raw_cache_should_not_run)

    docs = asyncio.run(
        neighborhood_routes._load_public_dataset_docs_bounded(
            "building_permits",
            120,
            neighborhood="Loop",
        )
    )

    assert [doc["id"] for doc in docs] == ["permit-loop-indexed"]


def test_public_dataset_index_prefers_mounted_cache(monkeypatch, tmp_path) -> None:
    from modal_app.api.services import documents

    documents.cache.invalidate_prefix("docs:")
    monkeypatch.setattr(documents, "get_processed_data_dir", lambda: tmp_path)
    mounted_doc = _public_doc("inspection-loop-mounted", "food_inspections", geo={"neighborhood": "Loop"})
    mounted_index = {
        "neighborhoods": {
            "Loop": {
                "food_inspections": [mounted_doc],
            }
        }
    }
    observed: list[str] = []

    def fake_load_json_file(path, default=None):
        observed.append(str(path))
        if str(path) == "/data/processed/cache/public_data_by_neighborhood.json":
            return mounted_index
        return default

    monkeypatch.setattr(documents, "load_json_file", fake_load_json_file)

    docs = documents.load_public_dataset_docs_for_neighborhood("food_inspections", "Loop", 20)

    assert [doc["id"] for doc in docs] == ["inspection-loop-mounted"]
    assert observed == ["/data/processed/cache/public_data_by_neighborhood.json"]


def test_modal_neighborhood_public_dataset_returns_empty_when_live_and_cached_fail(monkeypatch) -> None:
    import asyncio

    from modal_app.api.routes import neighborhoods as neighborhood_routes

    def fail_live_fetch(dataset: str, neighborhood: str, limit: int = 200) -> list[dict]:
        del dataset, neighborhood, limit
        raise RuntimeError("socrata unavailable")

    def fail_cached_fetch(dataset: str, limit: int = 200) -> list[dict]:
        del dataset, limit
        raise TimeoutError("volume read timed out")

    monkeypatch.setattr(neighborhood_routes, "load_public_dataset_docs_for_neighborhood", lambda *args, **kwargs: [])
    monkeypatch.setattr(neighborhood_routes, "load_live_public_dataset_docs", fail_live_fetch)
    monkeypatch.setattr(neighborhood_routes, "load_public_dataset_docs", fail_cached_fetch)

    docs = asyncio.run(
        neighborhood_routes._load_public_dataset_docs_bounded(
            "building_permits",
            120,
            neighborhood="Loop",
        )
    )

    assert docs == []


def test_modal_neighborhood_filter_does_not_treat_west_loop_as_loop() -> None:
    from modal_app.api.services.documents import filter_by_neighborhood

    docs = [
        {"id": "loop", "geo": {"neighborhood": "Loop"}, "metadata": {}, "title": "Loop listing", "content": ""},
        {"id": "west-loop", "geo": {"neighborhood": "West Loop"}, "metadata": {}, "title": "West Loop listing", "content": ""},
        {"id": "coord-loop", "geo": {"lat": "41.8819", "lng": "-87.6278"}, "metadata": {}, "title": "Coordinate only", "content": ""},
    ]

    assert [doc["id"] for doc in filter_by_neighborhood(docs, "Loop")] == ["loop", "coord-loop"]


def test_cta_ridership_cache_uses_latest_station_record() -> None:
    from modal_app.api.services.documents import cta_ridership_by_station_from_docs

    docs = [
        {
            "title": "Clark/Lake",
            "metadata": {
                "raw_record": {
                    "stationame": "Clark/Lake",
                    "month_beginning": "2026-04-01T00:00:00.000",
                    "avg_weekday_rides": "12000",
                }
            },
        },
        {
            "title": "Clark/Lake",
            "metadata": {
                "raw_record": {
                    "stationame": "Clark/Lake",
                    "month_beginning": "2026-05-01T00:00:00.000",
                    "avg_weekday_rides": "13500",
                }
            },
        },
    ]

    stations = cta_ridership_by_station_from_docs(docs)

    assert stations["clarklake"]["avg_weekday_rides"] == 13500
    assert stations["clarklake"]["timestamp"] == "2026-05-01T00:00:00.000"


def test_compute_transit_score_uses_cached_ridership(monkeypatch, tmp_path) -> None:
    from modal_app.api.services import documents
    from modal_app.common import NEIGHBORHOOD_CENTROIDS

    lat, lng = NEIGHBORHOOD_CENTROIDS["Loop"]
    documents.cache.invalidate_prefix("cta:")
    monkeypatch.setattr(documents, "get_processed_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        documents,
        "load_cta_stations",
        lambda: [
            {"station_name": "Clark/Lake", "lat": lat, "lng": lng},
            {"station_name": "Far Away", "lat": 41.6, "lng": -87.9},
        ],
    )
    monkeypatch.setattr(
        documents,
        "load_cta_ridership_by_station",
        lambda: {"clarklake": {"avg_weekday_rides": 13500}},
    )

    score = documents.compute_transit_score("Loop")

    assert score["stations_nearby"] == 1
    assert score["station_names"] == ["Clark/Lake"]
    assert score["total_daily_riders"] == 13500
    assert score["transit_score"] == 100


def test_load_cta_stations_prefers_mounted_cache(monkeypatch, tmp_path) -> None:
    from modal_app.api.services import documents

    documents.cache.invalidate_prefix("cta:")
    monkeypatch.setattr(documents, "get_processed_data_dir", lambda: tmp_path)
    observed: list[str] = []
    mounted_stations = [{"station_name": "Clark/Lake", "lat": 41.885, "lng": -87.631}]

    def fake_load_json_file(path, default=None):
        observed.append(str(path))
        if str(path) == "/data/processed/cache/cta_stations.json":
            return mounted_stations
        return default

    monkeypatch.setattr(documents, "load_json_file", fake_load_json_file)

    assert documents.load_cta_stations() == mounted_stations
    assert observed == ["/data/processed/cache/cta_stations.json"]


def test_load_cta_ridership_prefers_mounted_cache(monkeypatch, tmp_path) -> None:
    from modal_app.api.services import documents

    documents.cache.invalidate_prefix("cta:")
    monkeypatch.setattr(documents, "get_processed_data_dir", lambda: tmp_path)
    observed: list[str] = []
    mounted_payload = {"stations": {"clarklake": {"avg_weekday_rides": 13500}}}

    def fake_load_json_file(path, default=None):
        observed.append(str(path))
        if str(path) == "/data/processed/cache/cta_l_ridership_by_station.json":
            return mounted_payload
        return default

    monkeypatch.setattr(documents, "load_json_file", fake_load_json_file)

    assert documents.load_cta_ridership_by_station() == mounted_payload["stations"]
    assert observed == ["/data/processed/cache/cta_l_ridership_by_station.json"]


def test_live_public_dataset_loader_builds_docs_from_socrata(monkeypatch) -> None:
    import json
    import urllib.parse

    from modal_app.api.services import documents

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "inspection_id": "2638411",
                        "dba_name": "CHLOE CHICAGO",
                        "address": "1 S WACKER DR",
                        "inspection_date": "2026-06-11T00:00:00.000",
                        "results": "Not Ready",
                        "latitude": "41.88188622746245",
                        "longitude": "-87.63661833048015",
                        "location": {
                            "latitude": "41.88188622746245",
                            "longitude": "-87.63661833048015",
                        },
                    }
                ]
            ).encode("utf-8")

    observed_url = ""

    def fake_urlopen(request, timeout=0):
        nonlocal observed_url
        del timeout
        observed_url = request.full_url
        return FakeResponse()

    monkeypatch.setattr(documents.urllib.request, "urlopen", fake_urlopen)

    docs = documents.load_live_public_dataset_docs("food_inspections", "Loop", limit=3)

    parsed = urllib.parse.urlparse(observed_url)
    query = urllib.parse.parse_qs(parsed.query)
    assert query["$limit"] == ["3"]
    assert "within_circle(location,41.8819,-87.6278,2750)" in query["$where"][0]
    assert docs[0]["id"] == "public-food_inspections-2638411"
    assert docs[0]["metadata"]["dataset"] == "food_inspections"
    assert docs[0]["geo"]["lat"] == "41.88188622746245"
