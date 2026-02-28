"""Shared data models and constants for all Alethia Modal pipelines."""
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Coroutine

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    NEWS = "news"
    POLITICS = "politics"
    REDDIT = "reddit"
    YELP = "yelp"
    GOOGLE_PLACES = "google_places"
    PUBLIC_DATA = "public_data"
    DEMOGRAPHICS = "demographics"
    REAL_ESTATE = "real_estate"
    VISION = "vision"
    TRAFFIC = "traffic"


class Document(BaseModel):
    """Unified document schema for all ingested data."""
    id: str
    source: SourceType
    title: str
    content: str
    url: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)
    geo: dict = Field(default_factory=dict)  # neighborhood, ward, lat/lng


class RiskFactor(BaseModel):
    """Individual risk factor with explainable evidence."""
    source: SourceType
    category: str  # e.g. "zoning", "competition", "sentiment"
    description: str
    weight: float = Field(ge=0, le=1)  # 0-1
    severity: str = "medium"  # low, medium, high
    evidence_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    trend: str = "stable"  # improving, stable, worsening


class RiskScore(BaseModel):
    """Aggregated risk score for a neighborhood + business type."""
    neighborhood: str
    business_type: str
    overall_score: float = Field(ge=0, le=10)  # 0-10
    confidence: float = Field(ge=0, le=1)  # 0-1
    factors: list[RiskFactor] = Field(default_factory=list)
    summary: str = ""

    def breakdown_display(self) -> list[dict]:
        """Return factor breakdown for frontend display."""
        if not self.factors:
            return []
        total_weight = sum(f.weight for f in self.factors)
        return [
            {
                "label": f"{f.evidence_count} {f.category} signals",
                "pct": round((f.weight / total_weight) * 100) if total_weight > 0 else 0,
                "source": f.source.value,
                "severity": f.severity,
                "description": f.description,
            }
            for f in sorted(self.factors, key=lambda x: x.weight, reverse=True)
        ]


class NeighborhoodGeoMetrics(BaseModel):
    """Per-neighborhood aggregates for Mapbox heatmap consumption."""
    neighborhood: str
    regulatory_density: float = 0.0
    business_activity: float = 0.0
    sentiment: float = 0.0
    risk_score: float = 0.0
    active_permits: int = 0
    crime_incidents_30d: int = 0
    avg_review_rating: float = 0.0
    review_count: int = 0
    population: int = 0
    median_income: float = 0.0


class NeighborhoodVisionAnalysis(BaseModel):
    """Structured output from the custom neighborhood detector."""
    neighborhood: str
    foot_traffic_density: str  # "low" / "medium" / "high"
    vacancy_indicators: int  # count of closed storefronts + for-lease signs
    business_activity_score: int  # count of active businesses + restaurants
    development_activity: int  # construction count
    dining_scene: int  # restaurant signage + outdoor dining
    person_count: int
    vehicle_count: int
    source_video: str = ""  # YouTube URL used for training
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrafficFlowDataPoint(BaseModel):
    """Traffic flow reading at a specific location (neighborhood centroid)."""
    neighborhood: str
    lat: float
    lng: float
    current_speed: float  # mph
    free_flow_speed: float
    congestion_level: str  # "free", "moderate", "heavy", "blocked"
    current_travel_time: int  # seconds
    free_flow_travel_time: int
    confidence: float  # 0-1 confidence in measurement
    road_closure: bool = False
    is_anomaly: bool = False
    severity: str = "normal"  # "normal", "info", "warning", "critical"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Chicago neighborhoods for geo-tagging
CHICAGO_NEIGHBORHOODS = [
    "Albany Park", "Andersonville", "Avondale", "Beverly", "Boystown",
    "Bridgeport", "Bronzeville", "Bucktown", "Chatham", "Chinatown",
    "Douglas", "Edgewater", "Englewood", "Gold Coast", "Humboldt Park",
    "Hyde Park", "Irving Park", "Jefferson Park", "Kenwood", "Lakeview",
    "Lincoln Park", "Lincoln Square", "Little Italy", "Little Village",
    "Logan Square", "Loop", "Morgan Park", "Near North Side", "Near West Side",
    "North Center", "North Lawndale", "Old Town", "Pilsen", "Portage Park",
    "Pullman", "Ravenswood", "River North", "Rogers Park", "Roscoe Village",
    "South Loop", "South Shore", "Streeterville", "Ukrainian Village",
    "Uptown", "West Loop", "West Town", "Wicker Park", "Woodlawn",
]

# Neighborhood centroids for heatmap point placement (lat, lng)
NEIGHBORHOOD_CENTROIDS: dict[str, tuple[float, float]] = {
    "Albany Park": (41.9684, -87.7244),
    "Andersonville": (41.9800, -87.6685),
    "Avondale": (41.9387, -87.7112),
    "Boystown": (41.9456, -87.6498),
    "Bridgeport": (41.8381, -87.6513),
    "Bronzeville": (41.8169, -87.6185),
    "Bucktown": (41.9217, -87.6796),
    "Chinatown": (41.8517, -87.6338),
    "Edgewater": (41.9833, -87.6607),
    "Gold Coast": (41.9048, -87.6279),
    "Humboldt Park": (41.9025, -87.7209),
    "Hyde Park": (41.7943, -87.5907),
    "Lakeview": (41.9434, -87.6553),
    "Lincoln Park": (41.9214, -87.6513),
    "Lincoln Square": (41.9688, -87.6891),
    "Little Village": (41.8445, -87.7134),
    "Logan Square": (41.9233, -87.7083),
    "Loop": (41.8819, -87.6278),
    "Near North Side": (41.9003, -87.6345),
    "Old Town": (41.9112, -87.6380),
    "Pilsen": (41.8525, -87.6614),
    "River North": (41.8921, -87.6349),
    "Rogers Park": (42.0087, -87.6680),
    "South Loop": (41.8569, -87.6258),
    "Streeterville": (41.8929, -87.6178),
    "Ukrainian Village": (41.8986, -87.6871),
    "Uptown": (41.9656, -87.6536),
    "West Loop": (41.8826, -87.6499),
    "West Town": (41.8960, -87.6731),
    "Wicker Park": (41.9088, -87.6796),
}

# Socrata community area numbers → canonical neighborhood names
COMMUNITY_AREA_MAP: dict[int, str] = {
    1: "Rogers Park", 2: "West Ridge", 3: "Uptown", 4: "Lincoln Square",
    5: "North Center", 6: "Lakeview", 7: "Lincoln Park", 8: "Near North Side",
    9: "Edison Park", 10: "Norwood Park", 11: "Jefferson Park", 12: "Forest Glen",
    13: "North Park", 14: "Albany Park", 15: "Portage Park", 16: "Irving Park",
    17: "Dunning", 18: "Montclare", 19: "Belmont Cragin", 20: "Hermosa",
    21: "Avondale", 22: "Logan Square", 23: "Humboldt Park", 24: "West Town",
    25: "Austin", 26: "West Garfield Park", 27: "East Garfield Park",
    28: "Near West Side", 29: "North Lawndale", 30: "South Lawndale",
    31: "Lower West Side", 32: "Loop", 33: "Near South Side",
    34: "Armour Square", 35: "Douglas", 36: "Oakland", 37: "Fuller Park",
    38: "Grand Boulevard", 39: "Kenwood", 40: "Washington Park",
    41: "Hyde Park", 42: "Woodlawn", 43: "South Shore", 44: "Chatham",
    45: "Avalon Park", 46: "South Chicago", 47: "Burnside", 48: "Calumet Heights",
    49: "Roseland", 50: "Pullman", 51: "South Deering", 52: "East Side",
    53: "West Pullman", 54: "Riverdale", 55: "Hegewisch", 56: "Garfield Ridge",
    57: "Archer Heights", 58: "Brighton Park", 59: "McKinley Park",
    60: "Bridgeport", 61: "New City", 62: "West Elsdon", 63: "Gage Park",
    64: "Clearing", 65: "West Lawn", 66: "Chicago Lawn", 67: "West Englewood",
    68: "Englewood", 69: "Greater Grand Crossing", 70: "Ashburn",
    71: "Auburn Gresham", 72: "Beverly", 73: "Washington Heights",
    74: "Mount Greenwood", 75: "Morgan Park", 76: "O'Hare", 77: "Edgewater",
}

# Socrata dataset IDs for Chicago Data Portal
SOCRATA_DATASETS = {
    "business_licenses": "r5kz-chrr",
    "food_inspections": "4ijn-s7e5",
    "building_permits": "ydr8-5enu",
    "crimes": "ijzp-q8t2",
    "cta_ridership_L": "t2rn-p8d7",
    "cta_ridership_bus": "jyb9-n7fm",
    "business_owners": "ezma-pppn",
    "zoning": "unjd-c2ca",
}

# Reddit subreddits to monitor
REDDIT_SUBREDDITS = [
    "chicago",
    "chicagofood",
    "ChicagoNWside",
    "SouthSideChicago",
]


def detect_neighborhood(text: str) -> str:
    """Simple keyword match for geo-tagging free text.

    Returns the first matching canonical neighborhood name, or empty string.
    """
    if not text:
        return ""
    text_lower = text.lower()
    for neighborhood in CHICAGO_NEIGHBORHOODS:
        if neighborhood.lower() in text_lower:
            return neighborhood
    return ""


async def gather_with_limit(
    coros: list[Coroutine],
    max_concurrent: int = 5,
) -> list[Any]:
    """Async semaphore-bounded asyncio.gather() for parallel API calls.

    Limits concurrency to avoid rate limits and connection issues.
    Returns results in the same order as input coroutines.
    Failed coroutines return None instead of raising.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _limited(coro: Coroutine) -> Any:
        async with semaphore:
            try:
                return await coro
            except Exception as e:
                print(f"gather_with_limit task failed: {e}")
                return None

    return await asyncio.gather(*[_limited(c) for c in coros])
