"""Shared data models and constants for all Alethia Modal pipelines."""
from __future__ import annotations

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
    TIKTOK = "tiktok"


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
    status: str = "raw"  # lifecycle: "raw" → "enriched" → "graphed"


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

# Colloquial/sub-area names → community area number
# These are popular neighborhood names that don't match official CA names
NEIGHBORHOOD_TO_COMMUNITY_AREA: dict[str, int] = {
    "Wicker Park": 24,       # West Town
    "Bucktown": 24,          # West Town
    "Pilsen": 31,            # Lower West Side
    "River North": 8,        # Near North Side
    "West Loop": 28,         # Near West Side
    "Gold Coast": 8,         # Near North Side
    "Old Town": 7,           # Lincoln Park
    "Boystown": 6,           # Lakeview
    "Chinatown": 34,         # Armour Square
    "South Loop": 33,        # Near South Side
    "Streeterville": 8,      # Near North Side
    "Ukrainian Village": 24, # West Town
    "Little Italy": 28,      # Near West Side
    "Little Village": 30,    # South Lawndale
    "Andersonville": 77,     # Edgewater
    "Bronzeville": 35,       # Douglas
    "Ravenswood": 4,         # Lincoln Square
    "Roscoe Village": 5,     # North Center
}

# Pre-computed reverse lookup: neighborhood name (lower) → community area number string
_NAME_TO_CA: dict[str, str] = {}
for _num, _name in COMMUNITY_AREA_MAP.items():
    _NAME_TO_CA[_name.lower()] = str(_num)
for _name, _num in NEIGHBORHOOD_TO_COMMUNITY_AREA.items():
    _NAME_TO_CA[_name.lower()] = str(_num)


def neighborhood_to_ca(name: str) -> str:
    """Return community area number as string, or empty string if not found."""
    return _NAME_TO_CA.get(name.lower(), "")


# Census tract (6-digit FIPS) → community area number
# Source: Chicago Data Portal Census Tracts Boundaries (74p9-q2aq)
TRACT_TO_COMMUNITY_AREA: dict[str, int] = {
    "010100": 1, "010201": 1, "010202": 1, "010300": 1, "010400": 1,
    "010501": 1, "010502": 1, "010503": 1, "010600": 1, "010701": 1,
    "010702": 1, "020100": 2, "020200": 2, "020301": 2, "020302": 2,
    "020400": 2, "020500": 2, "020601": 2, "020602": 2, "020701": 2,
    "020702": 2, "020801": 2, "020802": 2, "020901": 2, "020902": 2,
    "030101": 77, "030102": 77, "030103": 77, "030104": 77, "030200": 77,
    "030300": 77, "030400": 77, "030500": 77, "030601": 77, "030603": 77,
    "030604": 77, "030701": 77, "030702": 77, "030703": 77, "030706": 77,
    "030800": 77, "030900": 77, "031000": 3, "031100": 3, "031200": 3,
    "031300": 3, "031400": 3, "031501": 3, "031502": 3, "031700": 3,
    "031800": 3, "031900": 3, "032100": 3, "040100": 4, "040201": 4,
    "040202": 4, "040300": 4, "040401": 4, "040402": 4, "040600": 4,
    "040700": 4, "040800": 4, "040900": 4, "050100": 5, "050200": 5,
    "050300": 5, "050500": 5, "050600": 5, "050700": 5, "050800": 5,
    "050900": 5, "051000": 5, "051100": 5, "051200": 5, "051300": 5,
    "051400": 5, "060100": 6, "060200": 6, "060300": 6, "060400": 6,
    "060500": 6, "060800": 6, "060900": 6, "061000": 6, "061100": 6,
    "061200": 6, "061500": 6, "061800": 6, "061901": 6, "061902": 6,
    "062000": 6, "062100": 6, "062200": 6, "062300": 6, "062400": 6,
    "062500": 6, "062600": 6, "062700": 6, "062800": 6, "062900": 6,
    "063000": 6, "063100": 6, "063200": 6, "063301": 6, "063302": 6,
    "063303": 6, "063400": 6, "070101": 7, "070102": 7, "070103": 7,
    "070200": 7, "070300": 7, "070400": 7, "070500": 7, "070600": 7,
    "070700": 7, "071000": 7, "071100": 7, "071200": 7, "071300": 7,
    "071400": 7, "071500": 7, "071600": 7, "071700": 7, "071800": 7,
    "080100": 8, "080201": 8, "080202": 8, "080300": 8, "080400": 8,
    "081000": 8, "081100": 8, "081201": 8, "081202": 8, "081300": 8,
    "081401": 8, "081402": 8, "081403": 8, "081500": 8, "081600": 8,
    "081700": 8, "081800": 8, "081900": 8, "090100": 9, "090200": 9,
    "090300": 9, "100100": 10, "100200": 10, "100300": 10, "100400": 10,
    "100500": 10, "100600": 10, "100700": 10, "110100": 11, "110200": 11,
    "110300": 11, "110400": 11, "110501": 11, "110502": 11, "120100": 12,
    "120200": 12, "120300": 12, "120400": 12, "130100": 13, "130200": 13,
    "130300": 13, "140100": 14, "140200": 14, "140301": 14, "140302": 14,
    "140400": 14, "140500": 14, "140601": 14, "140602": 14, "140701": 14,
    "140702": 14, "140800": 14, "150200": 15, "150300": 15, "150401": 15,
    "150402": 15, "150501": 15, "150502": 15, "150600": 15, "150700": 15,
    "150800": 15, "151001": 15, "151002": 15, "151100": 15, "151200": 15,
    "160100": 16, "160200": 16, "160300": 16, "160400": 16, "160501": 16,
    "160502": 16, "160601": 16, "160602": 16, "160700": 16, "160800": 16,
    "160900": 16, "161000": 16, "161100": 16, "161200": 16, "161300": 16,
    "170100": 17, "170200": 17, "170300": 17, "170400": 17, "170500": 17,
    "170600": 17, "170700": 17, "170800": 17, "170900": 17, "171000": 17,
    "171100": 17, "180100": 18, "190100": 19, "190200": 19, "190300": 19,
    "190401": 19, "190402": 19, "190601": 19, "190602": 19, "190701": 19,
    "190702": 19, "190800": 19, "190900": 19, "191000": 19, "191100": 19,
    "191200": 19, "191301": 19, "191302": 19, "200100": 20, "200200": 20,
    "200300": 20, "200401": 20, "200402": 20, "210100": 21, "210400": 21,
    "210501": 21, "210502": 21, "210601": 21, "210602": 21, "210700": 21,
    "210800": 21, "210900": 21, "220300": 22, "220400": 22, "220500": 22,
    "220601": 22, "220602": 22, "220701": 22, "220702": 22, "220901": 22,
    "220902": 22, "221000": 22, "221100": 22, "221200": 22, "221300": 22,
    "221400": 22, "221500": 22, "221600": 22, "222200": 22, "222500": 22,
    "222600": 22, "222700": 22, "222800": 22, "222900": 22, "230100": 23,
    "230200": 23, "230300": 23, "230400": 23, "230500": 23, "230600": 23,
    "230700": 23, "230800": 23, "230900": 23, "231100": 23, "231200": 23,
    "231500": 23, "240200": 24, "240300": 24, "240500": 24, "240600": 24,
    "240700": 24, "240800": 24, "240900": 24, "241000": 24, "241100": 24,
    "241200": 24, "241300": 24, "241400": 24, "241500": 24, "241600": 24,
    "242000": 24, "242100": 24, "242200": 24, "242300": 24, "242400": 24,
    "242500": 24, "242600": 24, "242700": 24, "242800": 24, "242900": 24,
    "243000": 24, "243100": 24, "243200": 24, "243300": 24, "243400": 24,
    "243500": 24, "250200": 25, "250300": 25, "250400": 25, "250500": 25,
    "250600": 25, "250700": 25, "250800": 25, "251000": 25, "251100": 25,
    "251200": 25, "251300": 25, "251400": 25, "251500": 25, "251600": 25,
    "251700": 25, "251800": 25, "251900": 25, "252000": 25, "252101": 25,
    "252102": 25, "252201": 25, "252202": 25, "260100": 26, "260200": 26,
    "260300": 26, "260400": 26, "260500": 26, "260600": 26, "260700": 26,
    "260800": 26, "260900": 26, "261000": 26, "270500": 27, "271200": 27,
    "271300": 27, "271400": 27, "271500": 27, "271800": 27, "280100": 28,
    "280400": 28, "280800": 28, "280900": 28, "281900": 28, "282700": 28,
    "282800": 28, "283100": 28, "283200": 28, "283800": 28, "290900": 29,
    "291200": 29, "291600": 29, "292200": 29, "292400": 29, "292500": 29,
    "300500": 30, "300600": 30, "300700": 30, "300800": 30, "300900": 30,
    "301100": 30, "301200": 30, "301600": 30, "301701": 30, "301702": 30,
    "301801": 30, "301802": 30, "301803": 30, "310200": 31, "310300": 31,
    "310400": 31, "310500": 31, "310600": 31, "310700": 31, "310800": 31,
    "310900": 31, "320100": 32, "320400": 32, "320600": 32, "330100": 33,
    "330200": 33, "340300": 34, "340400": 34, "340500": 34, "340600": 34,
    "350100": 35, "350400": 35, "351000": 35, "351100": 35, "351400": 35,
    "351500": 35, "360200": 36, "380100": 38, "380200": 38, "380500": 38,
    "380700": 38, "381200": 38, "381400": 38, "381500": 38, "381700": 38,
    "381800": 38, "381900": 38, "390100": 39, "390200": 39, "390300": 39,
    "390400": 39, "390500": 39, "390600": 39, "390700": 39, "400300": 40,
    "400400": 40, "400500": 40, "400800": 40, "410100": 41, "410200": 41,
    "410500": 41, "410600": 41, "410700": 41, "410800": 41, "410900": 41,
    "411000": 41, "411100": 41, "411200": 41, "420100": 42, "420200": 42,
    "420300": 42, "420400": 42, "420500": 42, "420600": 42, "420700": 42,
    "420800": 42, "421200": 42, "430101": 43, "430102": 43, "430200": 43,
    "430300": 43, "430400": 43, "430500": 43, "430600": 43, "430700": 43,
    "430800": 43, "430900": 43, "431200": 43, "431301": 43, "431302": 43,
    "431400": 43, "440101": 44, "440102": 44, "440201": 44, "440202": 44,
    "440300": 44, "440600": 44, "440700": 44, "440800": 44, "440900": 44,
    "450300": 45, "460100": 46, "460200": 46, "460301": 46, "460302": 46,
    "460400": 46, "460500": 46, "460600": 46, "460700": 46, "461000": 46,
    "470100": 47, "480100": 48, "480200": 48, "480300": 48, "480400": 48,
    "480500": 48, "490300": 49, "490400": 49, "490500": 49, "490600": 49,
    "490700": 49, "490800": 49, "490901": 49, "490902": 49, "491000": 49,
    "491100": 49, "491200": 49, "491300": 49, "491400": 49, "500100": 50,
    "500200": 50, "500300": 50, "510100": 51, "510200": 51, "510300": 51,
    "520100": 52, "520200": 52, "520300": 52, "520400": 52, "520500": 52,
    "520600": 52, "530100": 53, "530200": 53, "530300": 53, "530400": 53,
    "530501": 53, "530502": 53, "530503": 53, "530600": 53, "540101": 54,
    "540102": 54, "550100": 55, "550200": 55, "560100": 56, "560200": 56,
    "560300": 56, "560400": 56, "560700": 56, "560800": 56, "560900": 56,
    "561000": 56, "561100": 56, "570100": 57, "570200": 57, "570300": 57,
    "570400": 57, "570500": 57, "580100": 58, "580200": 58, "580300": 58,
    "580400": 58, "580501": 58, "580502": 58, "580600": 58, "580700": 58,
    "580800": 58, "590500": 59, "590600": 59, "590700": 59, "600400": 60,
    "600600": 60, "600700": 60, "600900": 60, "610300": 61, "610400": 61,
    "610800": 61, "611000": 61, "611100": 61, "611200": 61, "611300": 61,
    "611400": 61, "611500": 61, "611600": 61, "611700": 61, "611800": 61,
    "611900": 61, "612000": 61, "612100": 61, "620100": 62, "620200": 62,
    "620300": 62, "620400": 62, "630100": 63, "630200": 63, "630300": 63,
    "630400": 63, "630500": 63, "630800": 63, "630900": 63, "640100": 64,
    "640300": 64, "640400": 64, "640500": 64, "640600": 64, "640700": 64,
    "640800": 64, "650100": 65, "650200": 65, "650301": 65, "650302": 65,
    "650400": 65, "650500": 65, "660301": 66, "660302": 66, "660400": 66,
    "660500": 66, "660600": 66, "660700": 66, "660800": 66, "660900": 66,
    "661000": 66, "661100": 66, "670100": 67, "670200": 67, "670300": 67,
    "670400": 67, "670500": 67, "670600": 67, "670700": 67, "670800": 67,
    "670900": 67, "671100": 67, "671200": 67, "671300": 67, "671400": 67,
    "671500": 67, "671600": 67, "671800": 67, "671900": 67, "672000": 67,
    "680500": 68, "680600": 68, "680900": 68, "681000": 68, "681100": 68,
    "681200": 68, "681300": 68, "681400": 68, "690300": 69, "690400": 69,
    "690500": 69, "690900": 69, "691000": 69, "691100": 69, "691200": 69,
    "691300": 69, "691400": 69, "691500": 69, "700100": 70, "700200": 70,
    "700301": 70, "700302": 70, "700401": 70, "700402": 70, "700501": 70,
    "700502": 70, "710100": 71, "710200": 71, "710300": 71, "710400": 71,
    "710500": 71, "710600": 71, "710700": 71, "710800": 71, "710900": 71,
    "711000": 71, "711100": 71, "711200": 71, "711300": 71, "711400": 71,
    "711500": 71, "720100": 72, "720200": 72, "720300": 72, "720400": 72,
    "720500": 72, "720600": 72, "720700": 72, "730100": 73, "730201": 73,
    "730202": 73, "730300": 73, "730400": 73, "730500": 73, "730600": 73,
    "730700": 73, "740100": 74, "740200": 74, "740300": 74, "740400": 74,
    "750100": 75, "750200": 75, "750300": 75, "750400": 75, "750500": 75,
    "750600": 75, "760801": 76, "760802": 76, "760803": 76, "770602": 76,
    "770902": 76, "810400": 10, "821402": 53, "823304": 75, "830500": 30,
    "830600": 1, "830700": 3, "830800": 4, "830900": 22, "831000": 22,
    "831100": 21, "831200": 20, "831300": 25, "831400": 25, "831500": 19,
    "831600": 18, "831700": 15, "831800": 13, "831900": 6, "832000": 6,
    "832100": 6, "832200": 22, "832300": 22, "832400": 22, "832500": 7,
    "832600": 7, "832900": 28, "833000": 28, "833100": 28, "833300": 28,
    "833900": 46, "834000": 49, "834200": 43, "834300": 45, "834400": 42,
    "834500": 40, "834600": 68, "834700": 68, "834800": 68, "834900": 67,
    "835000": 66, "835100": 63, "835200": 56, "835500": 37, "835600": 37,
    "835700": 38, "835800": 38, "835900": 38, "836000": 38, "836100": 40,
    "836200": 41, "836300": 41, "836400": 36, "836500": 36, "836600": 23,
    "836700": 23, "836800": 27, "836900": 27, "837000": 27, "837100": 27,
    "837300": 27, "837400": 27, "837800": 28, "838000": 28, "838100": 28,
    "838200": 28, "838300": 8, "838600": 29, "838700": 29, "838800": 51,
    "839000": 32, "839100": 32, "839200": 35, "839500": 35, "839600": 35,
    "839700": 60, "839800": 60, "839900": 60, "840000": 60, "840100": 60,
    "840200": 60, "840300": 59, "840400": 59, "840700": 30, "840800": 30,
    "841000": 33, "841100": 34, "841200": 31, "841300": 31, "841400": 29,
    "841500": 29, "841600": 29, "841700": 30, "841800": 69, "841900": 28,
    "842000": 35, "842100": 23, "842200": 8, "842300": 24, "842400": 44,
    "842500": 69, "842600": 61, "842800": 58, "842900": 28, "843000": 29,
    "843100": 29, "843200": 31, "843300": 29, "843400": 29, "843500": 30,
    "843600": 38, "843700": 5, "843800": 61, "843900": 42, "980000": 76,
    "980100": 56,
}


def tract_to_neighborhood(tract_id: str) -> tuple[str, str]:
    """Map census tract → (community_area_str, neighborhood_name).

    Handles 2020 tract codes that split 2010 tracts by matching on the
    first 4 digits (Census Bureau preserves the base number when splitting).
    Returns ("", "") if tract not in crosswalk.
    """
    # Strategy 1: exact match (works for unsplit tracts)
    ca_num = TRACT_TO_COMMUNITY_AREA.get(tract_id)
    if ca_num is not None:
        return (str(ca_num), COMMUNITY_AREA_MAP.get(ca_num, ""))

    # Strategy 2: parent match — 2020 splits share first 4 digits with 2010 parent
    if len(tract_id) == 6:
        prefix = tract_id[:4]
        for code, ca in TRACT_TO_COMMUNITY_AREA.items():
            if code[:4] == prefix:
                return (str(ca), COMMUNITY_AREA_MAP.get(ca, ""))

    return ("", "")


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


async def safe_queue_push(queue, docs: list[dict], source: str) -> int:
    """Push docs to classification queue with logging. Returns failure count."""
    failures = 0
    for doc in docs:
        try:
            await queue.put.aio(doc)
        except Exception as e:
            failures += 1
            if failures == 1:
                print(f"safe_queue_push [{source}]: first failure: {e}")
    if failures:
        print(f"safe_queue_push [{source}]: {failures}/{len(docs)} failed")
    return failures


async def safe_volume_commit(vol, source: str) -> bool:
    """Commit volume with error logging. Returns True on success."""
    try:
        await vol.commit.aio()
        return True
    except Exception as e:
        print(f"safe_volume_commit [{source}]: failed: {e}")
        return False
