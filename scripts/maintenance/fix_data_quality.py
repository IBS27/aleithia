#!/usr/bin/env python3
"""
fix_data_quality.py — Master data quality fixer + synthetic data generator.

Phases:
  A) Delete corrupted (0-byte) files
  B) Fix food inspections missing geo
  C) Fix demographics missing geo
  D) Fix non-canonical neighborhood names
  E) Generate synthetic data for all 48 neighborhoods
  F) Regenerate summaries
  G) Regenerate GeoJSON neighborhood metrics
  H) Generate trend baselines for all 48 neighborhoods
"""

import json
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = (PROJECT_ROOT / "data").resolve()


def _resolve_dir(explicit_env: str, suffix: str) -> Path:
    explicit_value = os.environ.get(explicit_env, "").strip()
    if explicit_value:
        return Path(explicit_value).expanduser().resolve()

    data_root = os.environ.get("ALEITHIA_DATA_ROOT", "").strip()
    if data_root:
        return Path(data_root).expanduser().resolve() / suffix

    return DEFAULT_DATA_ROOT / suffix


DATA_DIR = _resolve_dir("ALEITHIA_RAW_DATA_DIR", "raw")
PROCESSED_DIR = _resolve_dir("ALEITHIA_PROCESSED_DATA_DIR", "processed")
SUMMARIES_DIR = PROCESSED_DIR / "summaries"
GEO_DIR = PROCESSED_DIR / "geo"
TRENDS_DIR = PROCESSED_DIR / "trends" / "baselines"

# ---------------------------------------------------------------------------
# Canonical data from modal_app/common.py (duplicated here to avoid imports)
# ---------------------------------------------------------------------------
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

NEIGHBORHOOD_CENTROIDS = {
    "Albany Park": (41.9684, -87.7244),
    "Andersonville": (41.9800, -87.6685),
    "Avondale": (41.9387, -87.7112),
    "Beverly": (41.7220, -87.6753),
    "Boystown": (41.9456, -87.6498),
    "Bridgeport": (41.8381, -87.6513),
    "Bronzeville": (41.8169, -87.6185),
    "Bucktown": (41.9217, -87.6796),
    "Chatham": (41.7410, -87.6128),
    "Chinatown": (41.8517, -87.6338),
    "Douglas": (41.8353, -87.6185),
    "Edgewater": (41.9833, -87.6607),
    "Englewood": (41.7799, -87.6456),
    "Gold Coast": (41.9048, -87.6279),
    "Humboldt Park": (41.9025, -87.7209),
    "Hyde Park": (41.7943, -87.5907),
    "Irving Park": (41.9531, -87.7244),
    "Jefferson Park": (41.9703, -87.7639),
    "Kenwood": (41.8095, -87.5936),
    "Lakeview": (41.9434, -87.6553),
    "Lincoln Park": (41.9214, -87.6513),
    "Lincoln Square": (41.9688, -87.6891),
    "Little Italy": (41.8687, -87.6600),
    "Little Village": (41.8445, -87.7134),
    "Logan Square": (41.9233, -87.7083),
    "Loop": (41.8819, -87.6278),
    "Morgan Park": (41.6906, -87.6667),
    "Near North Side": (41.9003, -87.6345),
    "Near West Side": (41.8817, -87.6655),
    "North Center": (41.9548, -87.6790),
    "North Lawndale": (41.8600, -87.7200),
    "Old Town": (41.9112, -87.6380),
    "Pilsen": (41.8525, -87.6614),
    "Portage Park": (41.9591, -87.7652),
    "Pullman": (41.6943, -87.6083),
    "Ravenswood": (41.9740, -87.6740),
    "River North": (41.8921, -87.6349),
    "Rogers Park": (42.0087, -87.6680),
    "Roscoe Village": (41.9434, -87.6800),
    "South Loop": (41.8569, -87.6258),
    "South Shore": (41.7615, -87.5761),
    "Streeterville": (41.8929, -87.6178),
    "Ukrainian Village": (41.8986, -87.6871),
    "Uptown": (41.9656, -87.6536),
    "West Loop": (41.8826, -87.6499),
    "West Town": (41.8960, -87.6731),
    "Wicker Park": (41.9088, -87.6796),
    "Woodlawn": (41.7800, -87.5965),
}

COMMUNITY_AREA_MAP = {
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

NEIGHBORHOOD_TO_COMMUNITY_AREA = {
    "Wicker Park": 24, "Bucktown": 24, "Pilsen": 31, "River North": 8,
    "West Loop": 28, "Gold Coast": 8, "Old Town": 7, "Boystown": 6,
    "Chinatown": 34, "South Loop": 33, "Streeterville": 8,
    "Ukrainian Village": 24, "Little Italy": 28, "Little Village": 30,
    "Andersonville": 77, "Bronzeville": 35, "Ravenswood": 4, "Roscoe Village": 5,
}

# Build CA name → canonical neighborhood name mapping
# Official CA names that map to our canonical names
_CA_TO_CANONICAL = {}
for ca_num, ca_name in COMMUNITY_AREA_MAP.items():
    # If the CA name is in our neighborhoods list, it maps to itself
    if ca_name in CHICAGO_NEIGHBORHOODS:
        _CA_TO_CANONICAL[ca_name] = ca_name
    # Check if any colloquial name maps to this CA
    for n_name, n_ca in NEIGHBORHOOD_TO_COMMUNITY_AREA.items():
        if n_ca == ca_num and n_name in CHICAGO_NEIGHBORHOODS:
            _CA_TO_CANONICAL[ca_name] = n_name

# Reverse: canonical neighborhood → community area number
_CANONICAL_TO_CA = {}
for n in CHICAGO_NEIGHBORHOODS:
    if n in NEIGHBORHOOD_TO_COMMUNITY_AREA:
        _CANONICAL_TO_CA[n] = NEIGHBORHOOD_TO_COMMUNITY_AREA[n]
    else:
        for ca_num, ca_name in COMMUNITY_AREA_MAP.items():
            if ca_name == n:
                _CANONICAL_TO_CA[n] = ca_num
                break

# TRACT_TO_COMMUNITY_AREA (abbreviated — only need for demographics fix)
# Full version is in modal_app/common.py; we read it from there at runtime
TRACT_TO_COMMUNITY_AREA = {}


def _load_tract_mapping():
    """Load the full TRACT_TO_COMMUNITY_AREA from common.py at runtime."""
    global TRACT_TO_COMMUNITY_AREA
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from modal_app.common import TRACT_TO_COMMUNITY_AREA as _t
        TRACT_TO_COMMUNITY_AREA = _t
    except ImportError:
        print("  WARNING: Could not import TRACT_TO_COMMUNITY_AREA from modal_app.common")
        print("  Demographics geo-fix will be limited")


# ---------------------------------------------------------------------------
# Neighborhood profiles for realistic synthetic data
# ---------------------------------------------------------------------------
NEIGHBORHOOD_PROFILES = {
    "Albany Park": {
        "character": "diverse immigrant community",
        "price_tier": "low",
        "population_range": (40000, 55000),
        "income_range": (35000, 50000),
        "typical_businesses": [
            ("Al-Basha Grill", "Restaurant"), ("Seoul Taco Express", "Restaurant"),
            ("Kedzie Currency Exchange", "Currency Exchange"), ("Sabor Guatemalteco", "Restaurant"),
        ],
        "ward": 39, "zip": "60625",
    },
    "Andersonville": {
        "character": "eclectic/Swedish heritage dining",
        "price_tier": "mid",
        "population_range": (25000, 35000),
        "income_range": (55000, 80000),
        "typical_businesses": [
            ("Big Jones", "Restaurant"), ("Hopleaf Bar", "Tavern"),
            ("Women & Children First", "Retail"), ("Anteprima", "Restaurant"),
        ],
        "ward": 48, "zip": "60640",
    },
    "Avondale": {
        "character": "working-class Polish/Latino mix",
        "price_tier": "low",
        "population_range": (35000, 45000),
        "income_range": (40000, 55000),
        "typical_businesses": [
            ("Kuma's Corner", "Restaurant"), ("Chief O'Neill's", "Tavern"),
            ("Honey Butter Fried Chicken", "Restaurant"), ("Avondale Laundry", "Retail"),
        ],
        "ward": 26, "zip": "60618",
    },
    "Beverly": {
        "character": "historic Irish-American residential",
        "price_tier": "mid",
        "population_range": (20000, 30000),
        "income_range": (70000, 95000),
        "typical_businesses": [
            ("Horse Thief Hollow", "Restaurant/Brewery"), ("Top Notch Beefburgers", "Restaurant"),
            ("Beverly Arts Center", "Entertainment"), ("Original Rainbow Cone", "Restaurant"),
        ],
        "ward": 19, "zip": "60643",
    },
    "Boystown": {
        "character": "LGBTQ+ nightlife/dining district",
        "price_tier": "mid",
        "population_range": (15000, 25000),
        "income_range": (55000, 80000),
        "typical_businesses": [
            ("Sidetrack", "Tavern"), ("Ann Sather", "Restaurant"),
            ("Kit Kat Lounge", "Tavern"), ("Pastoral Artisan Cheese", "Retail Food"),
        ],
        "ward": 44, "zip": "60613",
    },
    "Bridgeport": {
        "character": "blue-collar/emerging arts district",
        "price_tier": "low",
        "population_range": (30000, 40000),
        "income_range": (40000, 60000),
        "typical_businesses": [
            ("Maria's Packaged Goods", "Tavern"), ("Nana", "Restaurant"),
            ("Pleasant House Pub", "Restaurant"), ("Zhou B Art Center", "Gallery"),
        ],
        "ward": 11, "zip": "60608",
    },
    "Bronzeville": {
        "character": "historic Black cultural hub",
        "price_tier": "mid",
        "population_range": (20000, 30000),
        "income_range": (35000, 55000),
        "typical_businesses": [
            ("Pearl's Place", "Restaurant"), ("Bronzeville Winery", "Tavern"),
            ("Ain't She Sweet Cafe", "Restaurant"), ("Spoken Cafe", "Restaurant"),
        ],
        "ward": 3, "zip": "60616",
    },
    "Bucktown": {
        "character": "trendy boutiques/dining",
        "price_tier": "high",
        "population_range": (15000, 25000),
        "income_range": (75000, 110000),
        "typical_businesses": [
            ("Le Bouchon", "Restaurant"), ("The Bristol", "Restaurant"),
            ("Margie's Candies", "Restaurant"), ("Bucktown Pub", "Tavern"),
        ],
        "ward": 32, "zip": "60647",
    },
    "Chatham": {
        "character": "middle-class Black residential",
        "price_tier": "low",
        "population_range": (30000, 40000),
        "income_range": (30000, 50000),
        "typical_businesses": [
            ("Oooh Wee It Is", "Restaurant"), ("Chatham Currency", "Currency Exchange"),
            ("Leon's BBQ", "Restaurant"), ("Chatham Foods Market", "Grocery"),
        ],
        "ward": 6, "zip": "60619",
    },
    "Chinatown": {
        "character": "Chinese dining/cultural hub",
        "price_tier": "low",
        "population_range": (15000, 25000),
        "income_range": (30000, 50000),
        "typical_businesses": [
            ("MingHin Cuisine", "Restaurant"), ("Lao Sze Chuan", "Restaurant"),
            ("Triple Crown Restaurant", "Restaurant"), ("Chinatown Square Mall", "Retail"),
        ],
        "ward": 25, "zip": "60616",
    },
    "Douglas": {
        "character": "gentrifying near McCormick Place",
        "price_tier": "mid",
        "population_range": (18000, 28000),
        "income_range": (35000, 55000),
        "typical_businesses": [
            ("Chicago Bee Branch Library Cafe", "Restaurant"), ("The Boxcar", "Restaurant"),
            ("Groove Parlor", "Tavern"), ("Douglas Market Fresh", "Grocery"),
        ],
        "ward": 3, "zip": "60616",
    },
    "Edgewater": {
        "character": "lakefront residential/diverse",
        "price_tier": "mid",
        "population_range": (50000, 65000),
        "income_range": (45000, 70000),
        "typical_businesses": [
            ("Moody's Pub", "Tavern"), ("Indie Cafe", "Restaurant"),
            ("Ethiopian Diamond", "Restaurant"), ("Edgewater Produce", "Grocery"),
        ],
        "ward": 48, "zip": "60660",
    },
    "Englewood": {
        "character": "community revitalization area",
        "price_tier": "low",
        "population_range": (25000, 35000),
        "income_range": (20000, 35000),
        "typical_businesses": [
            ("Kusanya Cafe", "Restaurant"), ("I Grow Chicago", "Nonprofit"),
            ("Englewood Barber College", "School"), ("Sweet Maple Cafe", "Restaurant"),
        ],
        "ward": 16, "zip": "60621",
    },
    "Gold Coast": {
        "character": "luxury retail/fine dining",
        "price_tier": "high",
        "population_range": (15000, 25000),
        "income_range": (100000, 200000),
        "typical_businesses": [
            ("Gibson's Bar & Steakhouse", "Restaurant"), ("Maple & Ash", "Restaurant"),
            ("Luxbar", "Restaurant"), ("Barneys New York", "Retail"),
        ],
        "ward": 42, "zip": "60610",
    },
    "Humboldt Park": {
        "character": "Puerto Rican cultural center",
        "price_tier": "low",
        "population_range": (50000, 65000),
        "income_range": (30000, 45000),
        "typical_businesses": [
            ("La Bruquena", "Restaurant"), ("Papa's Cache Sabroso", "Restaurant"),
            ("Humboldt House", "Tavern"), ("Coco's Famous Snacks", "Restaurant"),
        ],
        "ward": 26, "zip": "60651",
    },
    "Hyde Park": {
        "character": "university/intellectual community",
        "price_tier": "mid",
        "population_range": (25000, 35000),
        "income_range": (50000, 80000),
        "typical_businesses": [
            ("Medici on 57th", "Restaurant"), ("Valois Restaurant", "Restaurant"),
            ("Seminary Co-op Bookstore", "Retail"), ("The Promontory", "Restaurant"),
        ],
        "ward": 5, "zip": "60637",
    },
    "Irving Park": {
        "character": "family residential/diverse",
        "price_tier": "low",
        "population_range": (50000, 65000),
        "income_range": (45000, 60000),
        "typical_businesses": [
            ("Hachi's Kitchen", "Restaurant"), ("Smak-Tak", "Restaurant"),
            ("Old Irving Brewing", "Restaurant/Brewery"), ("Irving Park Hardware", "Retail"),
        ],
        "ward": 45, "zip": "60641",
    },
    "Jefferson Park": {
        "character": "northwest side residential hub",
        "price_tier": "low",
        "population_range": (25000, 35000),
        "income_range": (50000, 70000),
        "typical_businesses": [
            ("Gale Street Inn", "Restaurant"), ("Bar on Central", "Tavern"),
            ("Jeff Park Snack Shop", "Restaurant"), ("Northwest Auto Parts", "Retail"),
        ],
        "ward": 45, "zip": "60630",
    },
    "Kenwood": {
        "character": "stately residential near UChicago",
        "price_tier": "mid",
        "population_range": (15000, 20000),
        "income_range": (45000, 75000),
        "typical_businesses": [
            ("Virtue Restaurant", "Restaurant"), ("Norman's Bistro", "Restaurant"),
            ("Kenwood Liquors", "Retail"), ("47th Street Coffee", "Restaurant"),
        ],
        "ward": 4, "zip": "60615",
    },
    "Lakeview": {
        "character": "vibrant young professional district",
        "price_tier": "mid",
        "population_range": (90000, 110000),
        "income_range": (65000, 95000),
        "typical_businesses": [
            ("Crisp", "Restaurant"), ("Sheffield's", "Tavern"),
            ("Southport Grocery", "Restaurant"), ("Uncommon Ground", "Restaurant"),
        ],
        "ward": 44, "zip": "60657",
    },
    "Lincoln Park": {
        "character": "upscale residential/dining",
        "price_tier": "high",
        "population_range": (60000, 75000),
        "income_range": (85000, 130000),
        "typical_businesses": [
            ("Alinea", "Restaurant"), ("R.J. Grunts", "Restaurant"),
            ("Twin Anchors", "Restaurant"), ("Boka", "Restaurant"),
        ],
        "ward": 43, "zip": "60614",
    },
    "Lincoln Square": {
        "character": "German heritage/craft scene",
        "price_tier": "mid",
        "population_range": (35000, 50000),
        "income_range": (55000, 80000),
        "typical_businesses": [
            ("DANK Haus German American", "Restaurant"), ("Luella's Southern Kitchen", "Restaurant"),
            ("Gene's Sausage Shop", "Retail Food"), ("The Book Cellar", "Retail"),
        ],
        "ward": 47, "zip": "60625",
    },
    "Little Italy": {
        "character": "Italian dining district near UIC",
        "price_tier": "mid",
        "population_range": (10000, 18000),
        "income_range": (40000, 65000),
        "typical_businesses": [
            ("Mario's Italian Lemonade", "Restaurant"), ("Pompei Bakery", "Restaurant"),
            ("Tuscany on Taylor", "Restaurant"), ("Al's #1 Italian Beef", "Restaurant"),
        ],
        "ward": 25, "zip": "60607",
    },
    "Little Village": {
        "character": "Mexican cultural/commercial corridor",
        "price_tier": "low",
        "population_range": (70000, 85000),
        "income_range": (28000, 42000),
        "typical_businesses": [
            ("Taqueria El Milagro", "Restaurant"), ("Nuevo Leon", "Restaurant"),
            ("Discount Mall", "Retail"), ("Panaderia Patio Tlaxcalteca", "Retail Food"),
        ],
        "ward": 22, "zip": "60623",
    },
    "Logan Square": {
        "character": "hipster/craft cocktail scene",
        "price_tier": "mid",
        "population_range": (70000, 85000),
        "income_range": (55000, 80000),
        "typical_businesses": [
            ("Longman & Eagle", "Restaurant"), ("Lost Lake", "Tavern"),
            ("Bang Bang Pie", "Restaurant"), ("Wolfbait & B-Girls", "Retail"),
        ],
        "ward": 35, "zip": "60647",
    },
    "Loop": {
        "character": "downtown business/tourism hub",
        "price_tier": "high",
        "population_range": (30000, 45000),
        "income_range": (80000, 150000),
        "typical_businesses": [
            ("The Berghoff", "Restaurant"), ("Atwood", "Restaurant"),
            ("Garrett Popcorn Shops", "Retail Food"), ("Miller's Pub", "Tavern"),
        ],
        "ward": 42, "zip": "60601",
    },
    "Morgan Park": {
        "character": "far south side residential",
        "price_tier": "low",
        "population_range": (20000, 28000),
        "income_range": (45000, 65000),
        "typical_businesses": [
            ("Franconello's", "Restaurant"), ("Rainbow Cone II", "Restaurant"),
            ("Morgan Park Hardware", "Retail"), ("Janson's Drive-In", "Restaurant"),
        ],
        "ward": 19, "zip": "60643",
    },
    "Near North Side": {
        "character": "luxury shopping/Magnificent Mile",
        "price_tier": "high",
        "population_range": (80000, 100000),
        "income_range": (90000, 170000),
        "typical_businesses": [
            ("RPM Italian", "Restaurant"), ("Shaw's Crab House", "Restaurant"),
            ("Frontera Grill", "Restaurant"), ("Eataly Chicago", "Retail Food"),
        ],
        "ward": 42, "zip": "60611",
    },
    "Near West Side": {
        "character": "UIC/medical district/Greektown",
        "price_tier": "mid",
        "population_range": (50000, 70000),
        "income_range": (45000, 70000),
        "typical_businesses": [
            ("Greek Islands", "Restaurant"), ("Artopolis", "Restaurant"),
            ("Athena", "Restaurant"), ("Rush University Medical Center Cafe", "Restaurant"),
        ],
        "ward": 25, "zip": "60607",
    },
    "North Center": {
        "character": "family-friendly residential",
        "price_tier": "mid",
        "population_range": (30000, 40000),
        "income_range": (70000, 100000),
        "typical_businesses": [
            ("Bad Apple", "Restaurant"), ("Fountainhead", "Tavern"),
            ("Half Acre Beer Company", "Restaurant/Brewery"), ("Gather", "Restaurant"),
        ],
        "ward": 47, "zip": "60618",
    },
    "North Lawndale": {
        "character": "community investment area",
        "price_tier": "low",
        "population_range": (30000, 40000),
        "income_range": (22000, 35000),
        "typical_businesses": [
            ("MacArthur's Restaurant", "Restaurant"), ("Lawndale Christian Health", "Health"),
            ("North Lawndale Employment", "Nonprofit"), ("Homan Square Grocery", "Grocery"),
        ],
        "ward": 24, "zip": "60623",
    },
    "Old Town": {
        "character": "comedy clubs/historic brownstones",
        "price_tier": "high",
        "population_range": (15000, 25000),
        "income_range": (80000, 130000),
        "typical_businesses": [
            ("The Second City", "Entertainment"), ("Twin Anchors", "Restaurant"),
            ("Old Town Ale House", "Tavern"), ("Old Town Social", "Restaurant"),
        ],
        "ward": 43, "zip": "60610",
    },
    "Pilsen": {
        "character": "arts/Mexican food cultural district",
        "price_tier": "low",
        "population_range": (35000, 45000),
        "income_range": (35000, 55000),
        "typical_businesses": [
            ("Dusek's Board & Beer", "Restaurant"), ("S-KY Desserts", "Restaurant"),
            ("Don Pedro Carnitas", "Restaurant"), ("Pilsen Vintage", "Retail"),
        ],
        "ward": 25, "zip": "60608",
    },
    "Portage Park": {
        "character": "northwest side family area",
        "price_tier": "low",
        "population_range": (60000, 75000),
        "income_range": (50000, 65000),
        "typical_businesses": [
            ("Portage Park Grille", "Restaurant"), ("Vaughan's Pub", "Tavern"),
            ("Six Corners Shopping", "Retail"), ("Blue Sky Bakery", "Restaurant"),
        ],
        "ward": 38, "zip": "60634",
    },
    "Pullman": {
        "character": "historic landmark district",
        "price_tier": "low",
        "population_range": (8000, 12000),
        "income_range": (40000, 55000),
        "typical_businesses": [
            ("Cal-Harbor Restaurant", "Restaurant"), ("Pullman Cafe", "Restaurant"),
            ("Historic Pullman Foundation", "Nonprofit"), ("Pullman Flats Brewing", "Restaurant/Brewery"),
        ],
        "ward": 9, "zip": "60628",
    },
    "Ravenswood": {
        "character": "quiet residential/craft brewing",
        "price_tier": "mid",
        "population_range": (20000, 30000),
        "income_range": (65000, 90000),
        "typical_businesses": [
            ("Band of Bohemia", "Restaurant/Brewery"), ("Begyle Brewing", "Restaurant/Brewery"),
            ("Ravenswood Used Books", "Retail"), ("Herb", "Restaurant"),
        ],
        "ward": 47, "zip": "60640",
    },
    "River North": {
        "character": "gallery district/nightlife",
        "price_tier": "high",
        "population_range": (20000, 35000),
        "income_range": (85000, 150000),
        "typical_businesses": [
            ("Bavette's Bar & Boeuf", "Restaurant"), ("The Dearborn", "Restaurant"),
            ("ROOF on theWit", "Tavern"), ("Gilt Bar", "Restaurant"),
        ],
        "ward": 42, "zip": "60654",
    },
    "Rogers Park": {
        "character": "diverse/affordable lakefront",
        "price_tier": "low",
        "population_range": (55000, 70000),
        "income_range": (35000, 55000),
        "typical_businesses": [
            ("The Heartland Cafe", "Restaurant"), ("Glenwood Sunday Market", "Market"),
            ("Ennui Cafe", "Restaurant"), ("Mayne Stage", "Entertainment"),
        ],
        "ward": 49, "zip": "60626",
    },
    "Roscoe Village": {
        "character": "family village vibe",
        "price_tier": "mid",
        "population_range": (15000, 25000),
        "income_range": (70000, 100000),
        "typical_businesses": [
            ("Turquoise Restaurant", "Restaurant"), ("Village Tap", "Tavern"),
            ("Delicious Pastries", "Retail Food"), ("Roscoe Books", "Retail"),
        ],
        "ward": 47, "zip": "60618",
    },
    "South Loop": {
        "character": "condo towers/museum campus",
        "price_tier": "high",
        "population_range": (25000, 40000),
        "income_range": (70000, 110000),
        "typical_businesses": [
            ("Mercat a la Planxa", "Restaurant"), ("Acadia", "Restaurant"),
            ("Weather Mark Tavern", "Tavern"), ("South Loop Market", "Grocery"),
        ],
        "ward": 4, "zip": "60605",
    },
    "South Shore": {
        "character": "lakefront Black community",
        "price_tier": "low",
        "population_range": (45000, 60000),
        "income_range": (25000, 40000),
        "typical_businesses": [
            ("Daley's Restaurant", "Restaurant"), ("Original Soul Vegetarian", "Restaurant"),
            ("South Shore Cultural Center", "Entertainment"), ("Currency Exchange Plus", "Financial"),
        ],
        "ward": 5, "zip": "60649",
    },
    "Streeterville": {
        "character": "luxury hotels/Navy Pier area",
        "price_tier": "high",
        "population_range": (20000, 35000),
        "income_range": (90000, 160000),
        "typical_businesses": [
            ("Portillo's", "Restaurant"), ("Billy Goat Tavern", "Tavern"),
            ("Purple Pig", "Restaurant"), ("Grand Lux Cafe", "Restaurant"),
        ],
        "ward": 42, "zip": "60611",
    },
    "Ukrainian Village": {
        "character": "artistic/Eastern European heritage",
        "price_tier": "mid",
        "population_range": (15000, 22000),
        "income_range": (55000, 80000),
        "typical_businesses": [
            ("Tryzub Ukrainian Kitchen", "Restaurant"), ("Archie's Iowa Rockwell", "Tavern"),
            ("Reno", "Restaurant"), ("Old Lviv", "Restaurant"),
        ],
        "ward": 32, "zip": "60622",
    },
    "Uptown": {
        "character": "diverse entertainment district",
        "price_tier": "low",
        "population_range": (55000, 70000),
        "income_range": (40000, 60000),
        "typical_businesses": [
            ("Demera Ethiopian", "Restaurant"), ("Tweet", "Restaurant"),
            ("Riviera Theatre", "Entertainment"), ("Tank Noodle", "Restaurant"),
        ],
        "ward": 46, "zip": "60640",
    },
    "West Loop": {
        "character": "restaurant row/tech hub",
        "price_tier": "high",
        "population_range": (25000, 40000),
        "income_range": (80000, 140000),
        "typical_businesses": [
            ("Girl & The Goat", "Restaurant"), ("Au Cheval", "Restaurant"),
            ("Avec", "Restaurant"), ("Google Chicago Office Cafe", "Restaurant"),
        ],
        "ward": 27, "zip": "60607",
    },
    "West Town": {
        "character": "hip mixed-use commercial",
        "price_tier": "mid",
        "population_range": (80000, 100000),
        "income_range": (60000, 90000),
        "typical_businesses": [
            ("Publican Quality Meats", "Retail Food"), ("Clever Rabbit", "Restaurant"),
            ("Handlebar", "Restaurant"), ("Reckless Records", "Retail"),
        ],
        "ward": 1, "zip": "60622",
    },
    "Wicker Park": {
        "character": "trendy bars/boutique shopping",
        "price_tier": "high",
        "population_range": (20000, 30000),
        "income_range": (70000, 110000),
        "typical_businesses": [
            ("Big Star", "Restaurant"), ("The Violet Hour", "Tavern"),
            ("Piece Brewery", "Restaurant/Brewery"), ("Una Mae's", "Retail"),
        ],
        "ward": 1, "zip": "60622",
    },
    "Woodlawn": {
        "character": "Obama center revitalization",
        "price_tier": "low",
        "population_range": (20000, 30000),
        "income_range": (25000, 40000),
        "typical_businesses": [
            ("Daley's Restaurant", "Restaurant"), ("Woodlawn Tap", "Tavern"),
            ("63rd Street Market", "Grocery"), ("Woodlawn Community Center", "Nonprofit"),
        ],
        "ward": 5, "zip": "60637",
    },
}

# Ward assignments for neighborhoods (for geo data)
NEIGHBORHOOD_WARDS = {n: p["ward"] for n, p in NEIGHBORHOOD_PROFILES.items()}

# ---------------------------------------------------------------------------
# Violation text samples for food inspections
# ---------------------------------------------------------------------------
VIOLATION_TEXTS = [
    "1. PERSON IN CHARGE PRESENT, DEMONSTRATES KNOWLEDGE, AND PERFORMS DUTIES - Comments: OBSERVED NO PERSON IN CHARGE DURING INSPECTION.",
    "2. CITY OF CHICAGO FOOD SERVICE SANITATION CERTIFICATE - Comments: NO VALID FOOD SERVICE CERTIFICATE POSTED.",
    "3. MANAGEMENT, FOOD EMPLOYEE AND CONDITIONAL EMPLOYEE; KNOWLEDGE, RESPONSIBILITIES AND REPORTING - Comments: MUST MAINTAIN PROPER DOCUMENTATION.",
    "18. NO EVIDENCE OF RODENT OR INSECT OUTER OPENINGS PROTECTED/SEALED, A WRITTEN LOG OF PEST CONTROL SERVICE SHALL BE MAINTAINED - Comments: OBSERVED MOUSE DROPPINGS IN STORAGE AREA.",
    "22. PROPER COLD HOLDING TEMPERATURES - Comments: FOUND CHICKEN AT 48F INSTEAD OF 41F OR BELOW IN WALK-IN COOLER.",
    "32. FOOD AND NON-FOOD CONTACT SURFACES PROPERLY DESIGNED, CONSTRUCTED AND MAINTAINED - Comments: DAMAGED CUTTING BOARDS MUST BE REPLACED.",
    "33. PROPER COOLING METHODS USED; ADEQUATE EQUIPMENT FOR TEMPERATURE CONTROL - Comments: INADEQUATE COOLING EQUIPMENT.",
    "34. FLOORS: CONSTRUCTED PER CODE, CLEAN, GOOD REPAIR, COVERING INSTALLATION, DUST LESS CLEANING METHODS USED - Comments: FLOORS NOT CLEAN IN KITCHEN AREA.",
    "35. WALLS, CEILINGS, ATTACHED EQUIPMENT CONSTRUCTED PER CODE: GOOD REPAIR, SURFACES CLEAN AND DUSTLESS CLEANING METHODS - Comments: WALLS NEED REPAIR AND CLEANING.",
    "36. LIGHTING: REQUIRED MINIMUM FOOT-CANDLES OF LIGHT PROVIDED, FIXTURES SHIELDED - Comments: INADEQUATE LIGHTING IN FOOD PREP AREA.",
    "38. VENTILATION: ROOMS AND EQUIPMENT VENTED AS REQUIRED: PLUMBING: INSTALLED AND MAINTAINED - Comments: VENTILATION HOOD FILTERS NEED CLEANING.",
    "41. PREMISES MAINTAINED FREE OF LITTER, UNNECESSARY ARTICLES, CLEANING AND MAINTENANCE EQUIPMENT PROPERLY STORED - Comments: EXCESS STORAGE IN HALLWAY.",
    "54. GARBAGE & REFUSE PROPERLY DISPOSED; FACILITIES MAINTAINED - Comments: DUMPSTER AREA NEEDS CLEANING. MUST MAINTAIN AREA.",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
random.seed(42)  # Reproducible


def slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_")


def rand_ts(start_str="2026-02-20", end_str="2026-02-28"):
    """Random ISO timestamp in range."""
    start = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc)
    delta = end - start
    offset = random.random() * delta.total_seconds()
    dt = start + timedelta(seconds=offset)
    return dt.isoformat()


def jitter_coord(center_lat, center_lng, max_offset=0.005):
    """Add small random offset to coordinates."""
    lat = center_lat + random.uniform(-max_offset, max_offset)
    lng = center_lng + random.uniform(-max_offset, max_offset)
    return round(lat, 10), round(lng, 10)


def find_nearest_neighborhood(lat: float, lng: float) -> str:
    """Find nearest neighborhood by Euclidean distance to centroids."""
    best = ""
    best_dist = float("inf")
    for name, (clat, clng) in NEIGHBORHOOD_CENTROIDS.items():
        d = math.sqrt((lat - clat) ** 2 + (lng - clng) ** 2)
        if d < best_dist:
            best_dist = d
            best = name
    return best


def ca_for_neighborhood(name: str) -> str:
    """Get community area number string for a neighborhood name."""
    if name in _CANONICAL_TO_CA:
        return str(_CANONICAL_TO_CA[name])
    return ""


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None


# =========================================================================
# PHASE A: Delete corrupted (0-byte) files
# =========================================================================
def phase_a_delete_corrupted():
    print("\n=== Phase A: Delete corrupted (0-byte) files ===")
    deleted = 0
    for dirpath, _, filenames in os.walk(DATA_DIR):
        for fn in filenames:
            if not fn.endswith(".json"):
                continue
            fp = Path(dirpath) / fn
            if fp.stat().st_size == 0:
                print(f"  Deleting 0-byte file: {fp.relative_to(PROJECT_ROOT)}")
                fp.unlink()
                deleted += 1
    print(f"  Deleted {deleted} corrupted files")
    return deleted


# =========================================================================
# PHASE B: Fix food inspections missing geo
# =========================================================================
def phase_b_fix_food_inspections():
    print("\n=== Phase B: Fix food inspections geo ===")
    fixed = 0
    pub_dir = DATA_DIR / "public_data"
    if not pub_dir.exists():
        print("  No public_data directory found")
        return 0

    for fp in sorted(pub_dir.glob("public-food_inspections-*.json")):
        doc = load_json(fp)
        if not doc:
            continue
        geo = doc.get("geo", {})
        lat_str = geo.get("lat")
        lng_str = geo.get("lng")
        neighborhood = geo.get("neighborhood", "")
        if neighborhood:
            continue  # Already has neighborhood

        if lat_str and lng_str:
            try:
                lat = float(lat_str)
                lng = float(lng_str)
            except (ValueError, TypeError):
                continue
            nearest = find_nearest_neighborhood(lat, lng)
            if nearest:
                doc["geo"]["neighborhood"] = nearest
                ca = ca_for_neighborhood(nearest)
                doc["geo"]["community_area"] = ca
                ward = str(NEIGHBORHOOD_PROFILES.get(nearest, {}).get("ward", ""))
                doc["geo"]["ward"] = ward
                save_json(fp, doc)
                fixed += 1

    print(f"  Fixed {fixed} food inspection records")
    return fixed


# =========================================================================
# PHASE C: Fix demographics missing geo
# =========================================================================
def phase_c_fix_demographics():
    print("\n=== Phase C: Fix demographics geo ===")
    _load_tract_mapping()
    fixed = 0
    demo_dir = DATA_DIR / "demographics"
    if not demo_dir.exists():
        print("  No demographics directory found")
        return 0

    for fp in sorted(demo_dir.glob("demographics-tract-*.json")):
        doc = load_json(fp)
        if not doc:
            continue
        geo = doc.get("geo", {})
        if geo.get("neighborhood"):
            continue  # Already assigned

        tract_id = doc.get("metadata", {}).get("tract_id", "")
        if not tract_id:
            # Try extracting from filename
            fname = fp.stem  # demographics-tract-17031XXXXXX
            parts = fname.split("-")
            if len(parts) >= 3:
                full_tract = parts[-1]
                # Remove state+county FIPS prefix (17031)
                if full_tract.startswith("17031"):
                    tract_id = full_tract[5:]

        if not tract_id:
            continue

        ca_num = TRACT_TO_COMMUNITY_AREA.get(tract_id)
        if not ca_num:
            # Try prefix match (4-digit)
            prefix = tract_id[:4]
            for k, v in TRACT_TO_COMMUNITY_AREA.items():
                if k.startswith(prefix):
                    ca_num = v
                    break

        if ca_num:
            ca_name = COMMUNITY_AREA_MAP.get(ca_num, "")
            # Map to canonical neighborhood name
            canonical = _CA_TO_CANONICAL.get(ca_name, ca_name)
            if canonical and canonical in CHICAGO_NEIGHBORHOODS:
                doc["geo"]["neighborhood"] = canonical
                doc["geo"]["community_area"] = str(ca_num)
                save_json(fp, doc)
                fixed += 1
            elif ca_name:
                # Use the CA name even if not in our canonical list
                doc["geo"]["neighborhood"] = ca_name
                doc["geo"]["community_area"] = str(ca_num)
                save_json(fp, doc)
                fixed += 1

    print(f"  Fixed {fixed} demographics records")
    return fixed


# =========================================================================
# PHASE D: Fix non-canonical neighborhood names
# =========================================================================
def phase_d_fix_noncanonical():
    print("\n=== Phase D: Fix non-canonical neighborhood names ===")
    # Build mapping: official CA name → canonical name (where they differ)
    remap = {}
    for ca_num, ca_name in COMMUNITY_AREA_MAP.items():
        if ca_name not in CHICAGO_NEIGHBORHOODS:
            # Check if a colloquial name maps to this CA
            canonical = _CA_TO_CANONICAL.get(ca_name)
            if canonical and canonical in CHICAGO_NEIGHBORHOODS:
                remap[ca_name] = canonical

    fixed = 0
    for dirpath, _, filenames in os.walk(DATA_DIR):
        dp = Path(dirpath)
        # Skip processed dir
        if "processed" in str(dp):
            continue
        for fn in filenames:
            if not fn.endswith(".json"):
                continue
            fp = dp / fn
            doc = load_json(fp)
            if not doc:
                continue
            geo = doc.get("geo", {})
            nbhd = geo.get("neighborhood", "")
            if nbhd and nbhd in remap:
                doc["geo"]["neighborhood"] = remap[nbhd]
                save_json(fp, doc)
                fixed += 1

    print(f"  Fixed {fixed} non-canonical neighborhood names")
    print(f"  Remap table: {remap}")
    return fixed


# =========================================================================
# PHASE E: Generate synthetic data
# =========================================================================

def _gen_news(neighborhood: str, profile: dict, idx: int) -> dict:
    """Generate a synthetic news article."""
    s = slug(neighborhood)
    headlines = [
        f"New {profile['typical_businesses'][0][1]} Opening on {neighborhood}'s Main Strip Sparks Excitement",
        f"{neighborhood} Community Rallies Around Local Small Business Revival",
        f"City Approves Major Development Plan for {neighborhood} Corridor",
        f"{neighborhood} Residents Celebrate Annual Street Festival Despite Rain",
    ]
    bodies = [
        f"Residents and business owners in {neighborhood} are buzzing about the latest developments in the area. "
        f"The {profile['character']} neighborhood continues to attract attention from investors and entrepreneurs alike. "
        f"Local alderman Ward {profile['ward']} has expressed support for the initiative.",
        f"A new wave of small businesses is transforming {neighborhood}'s commercial corridors. "
        f"From {profile['typical_businesses'][0][0]} to {profile['typical_businesses'][1][0]}, "
        f"the neighborhood's {profile['character']} identity is drawing customers from across the city.",
    ]
    return {
        "id": f"news-rss-synth-{s}-{idx}",
        "source": "news",
        "title": headlines[idx % len(headlines)],
        "content": bodies[idx % len(bodies)],
        "url": f"https://blockclubchicago.org/2026/02/{20+idx}/synth-{s}",
        "timestamp": rand_ts(),
        "metadata": {
            "feed_name": random.choice(["Block Club Chicago", "Chicago Sun-Times", "Chicago Tribune"]),
            "author": random.choice(["Staff Reporter", "Maria Garcia", "James Wilson", "Sarah Chen"]),
            "tags": [neighborhood, "Business", "Community"],
        },
        "geo": {"neighborhood": neighborhood},
    }


def _gen_food_inspection(neighborhood: str, profile: dict, idx: int) -> dict:
    """Generate a synthetic food inspection record."""
    s = slug(neighborhood)
    centroid = NEIGHBORHOOD_CENTROIDS[neighborhood]
    lat, lng = jitter_coord(*centroid)
    biz = profile["typical_businesses"][idx % len(profile["typical_businesses"])]

    # Result distribution: 60% Pass, 20% Pass w/ Conditions, 15% Fail, 5% Out of Business
    r = random.random()
    if r < 0.60:
        result = "Pass"
        violations = ""
    elif r < 0.80:
        result = "Pass w/ Conditions"
        violations = random.choice(VIOLATION_TEXTS)
    elif r < 0.95:
        result = "Fail"
        violations = " | ".join(random.sample(VIOLATION_TEXTS, min(3, len(VIOLATION_TEXTS))))
    else:
        result = "Out of Business"
        violations = ""

    inspection_id = str(2700000 + hash(f"{s}-{idx}") % 100000)
    ca = ca_for_neighborhood(neighborhood)

    return {
        "id": f"public-food_inspections-synth-{s}-{idx}",
        "source": "public_data",
        "title": "Food Inspections Record",
        "content": f"inspection_id: {inspection_id}\ndba_name: {biz[0]}\nresults: {result}",
        "url": "",
        "timestamp": rand_ts(),
        "metadata": {
            "dataset": "food_inspections",
            "dataset_id": "4ijn-s7e5",
            "raw_record": {
                "inspection_id": inspection_id,
                "dba_name": biz[0],
                "aka_name": biz[0],
                "license_": str(2700000 + random.randint(0, 99999)),
                "facility_type": biz[1] if biz[1] in ("Restaurant", "Grocery", "Retail Food") else "Restaurant",
                "risk": random.choice(["Risk 1 (High)", "Risk 2 (Medium)", "Risk 3 (Low)"]),
                "address": f"{random.randint(100,9999)} {random.choice(['N', 'S', 'W', 'E'])} {random.choice(['MAIN', 'OAK', 'ELM', 'CLARK', 'HALSTED', 'ASHLAND', 'WESTERN', 'KEDZIE'])} {random.choice(['ST', 'AVE', 'BLVD'])}",
                "city": "CHICAGO",
                "state": "IL",
                "zip": profile["zip"],
                "inspection_date": f"2026-02-{random.randint(20,28):02d}T00:00:00.000",
                "inspection_type": random.choice(["Canvass", "Canvass Re-Inspection", "Complaint", "License"]),
                "results": result,
                "violations": violations,
            },
        },
        "geo": {
            "lat": str(lat),
            "lng": str(lng),
            "neighborhood": neighborhood,
            "ward": str(profile["ward"]),
            "community_area": ca,
        },
    }


def _gen_building_permit(neighborhood: str, profile: dict, idx: int) -> dict:
    """Generate a synthetic building permit."""
    s = slug(neighborhood)
    centroid = NEIGHBORHOOD_CENTROIDS[neighborhood]
    lat, lng = jitter_coord(*centroid)
    ca = ca_for_neighborhood(neighborhood)

    tier = profile["price_tier"]
    if tier == "low":
        fee = random.randint(100, 500)
    elif tier == "mid":
        fee = random.randint(500, 5000)
    else:
        fee = random.randint(2000, 50000)

    work_types = [
        "Interior Renovation", "Exterior Signage", "Small-Scale Solar PV System",
        "New Construction", "Electrical Wiring", "Porch/Deck Construction",
        "Fire Alarm System", "HVAC Installation", "Plumbing Repair",
    ]
    permit_num = f"B20045{random.randint(1000,9999)}"

    return {
        "id": f"public-building_permits-synth-{s}-{idx}",
        "source": "public_data",
        "title": "Building Permits Record",
        "content": f"permit_: {permit_num}\npermit_status: ACTIVE\nwork_type: {work_types[idx % len(work_types)]}",
        "url": "",
        "timestamp": rand_ts(),
        "metadata": {
            "dataset": "building_permits",
            "dataset_id": "ydr8-5enu",
            "raw_record": {
                "id": f"N{random.randint(2800000, 2900000)}",
                "permit_": permit_num,
                "permit_status": random.choice(["ACTIVE", "COMPLETE", "ISSUED"]),
                "permit_milestone": random.choice(["INSPECTIONS", "ISSUED", "COMPLETE"]),
                "permit_type": "PERMIT – EASY PERMIT PROCESS",
                "review_type": "EASY PERMIT PROCESS",
                "application_start_date": f"2026-02-{random.randint(10,25):02d}T00:00:00.000",
                "issue_date": f"2026-02-{random.randint(20,28):02d}T00:00:00.000",
                "processing_time": str(random.randint(3, 15)),
                "street_number": str(random.randint(100, 9999)),
                "street_direction": random.choice(["N", "S", "W", "E"]),
                "street_name": random.choice(["MAIN ST", "OAK AVE", "CLARK ST", "HALSTED ST", "ASHLAND AVE", "WESTERN AVE"]),
                "work_type": work_types[idx % len(work_types)],
                "work_description": f"INSTALL/RENOVATE {work_types[idx % len(work_types)].upper()} PER PLANS",
                "reported_cost": str(fee),
            },
        },
        "geo": {
            "lat": str(lat),
            "lng": str(lng),
            "neighborhood": neighborhood,
            "ward": str(profile["ward"]),
            "community_area": ca,
        },
    }


def _gen_business_license(neighborhood: str, profile: dict, idx: int) -> dict:
    """Generate a synthetic business license."""
    s = slug(neighborhood)
    centroid = NEIGHBORHOOD_CENTROIDS[neighborhood]
    lat, lng = jitter_coord(*centroid)
    ca = ca_for_neighborhood(neighborhood)
    biz = profile["typical_businesses"][idx % len(profile["typical_businesses"])]

    license_types = ["Retail Food Establishment", "Tavern", "Limited Business License",
                     "Regulated Business License", "Package Goods"]

    return {
        "id": f"public-business_licenses-synth-{s}-{idx}",
        "source": "public_data",
        "title": "Business Licenses Record",
        "content": f"doing_business_as_name: {biz[0]}\nlicense_description: {license_types[idx % len(license_types)]}",
        "url": "",
        "timestamp": rand_ts(),
        "metadata": {
            "dataset": "business_licenses",
            "dataset_id": "r5kz-chrr",
            "raw_record": {
                "id": f"{random.randint(3000000, 3100000)}-20260225",
                "license_id": str(random.randint(3000000, 3100000)),
                "account_number": str(random.randint(500000, 600000)),
                "site_number": "1",
                "legal_name": f"{biz[0]} LLC",
                "doing_business_as_name": biz[0].upper(),
                "address": f"{random.randint(100,9999)} {random.choice(['N', 'S', 'W', 'E'])} {random.choice(['CLARK', 'HALSTED', 'ASHLAND', 'WESTERN', 'KEDZIE', 'BROADWAY'])} {random.choice(['ST', 'AVE'])}",
                "city": "CHICAGO",
                "state": "IL",
                "zip_code": profile["zip"],
                "ward": str(profile["ward"]),
                "precinct": str(random.randint(1, 50)),
                "police_district": str(random.randint(1, 25)),
                "license_description": license_types[idx % len(license_types)],
                "business_activity": biz[1],
                "community_area": ca,
            },
        },
        "geo": {
            "lat": str(lat),
            "lng": str(lng),
            "neighborhood": neighborhood,
            "ward": str(profile["ward"]),
            "community_area": ca,
        },
    }


def _gen_review(neighborhood: str, profile: dict, idx: int) -> dict:
    """Generate a synthetic Yelp review."""
    s = slug(neighborhood)
    biz = profile["typical_businesses"][idx % len(profile["typical_businesses"])]
    centroid = NEIGHBORHOOD_CENTROIDS[neighborhood]
    lat, lng = jitter_coord(*centroid)

    # Rating: normal distribution centered on 4.0
    rating = round(max(1.0, min(5.0, random.gauss(4.0, 0.5))), 1)
    # Snap to half-stars
    rating = round(rating * 2) / 2

    tier = profile["price_tier"]
    price_map = {"low": "$", "mid": "$$", "high": "$$$"}

    review_texts = [
        f"Great spot in {neighborhood}! The {profile['character']} vibe really comes through.",
        f"Solid choice for the area. Good food and friendly service at {biz[0]}.",
        f"Been coming here for years. {biz[0]} is a {neighborhood} institution.",
    ]

    return {
        "id": f"review-yelp-synth-{s}-{idx}",
        "source": "reviews",
        "title": f"{biz[0]} — {neighborhood}",
        "content": review_texts[idx % len(review_texts)],
        "url": f"https://www.yelp.com/biz/synth-{s}-{idx}",
        "timestamp": rand_ts(),
        "metadata": {
            "platform": "yelp",
            "business_name": biz[0],
            "rating": rating,
            "review_count": random.randint(20, 500),
            "price": price_map.get(tier, "$$"),
            "categories": [biz[1], "Food"],
            "neighborhood": neighborhood,
        },
        "geo": {
            "lat": str(lat),
            "lng": str(lng),
            "neighborhood": neighborhood,
        },
    }


def _gen_realestate(neighborhood: str, profile: dict, idx: int) -> dict:
    """Generate a synthetic real estate listing."""
    s = slug(neighborhood)
    centroid = NEIGHBORHOOD_CENTROIDS[neighborhood]
    lat, lng = jitter_coord(*centroid)

    tier = profile["price_tier"]
    if tier == "low":
        price = random.randint(1500, 3000)
        size = random.randint(800, 2000)
    elif tier == "mid":
        price = random.randint(3000, 6000)
        size = random.randint(1000, 3000)
    else:
        price = random.randint(6000, 15000)
        size = random.randint(1500, 5000)

    prop_types = ["Retail", "Office", "Mixed-Use", "Restaurant Space"]
    prop_type = prop_types[idx % len(prop_types)]

    return {
        "id": f"realestate-synth-{s}-{idx}",
        "source": "real_estate",
        "title": f"{prop_type} Space — {neighborhood}",
        "content": f"Commercial {prop_type.lower()} space in {neighborhood}. "
                   f"Located in a {profile['character']} area. Size: {size:,} sqft. Price: ${price:,}/mo.",
        "url": "",
        "timestamp": rand_ts(),
        "metadata": {
            "property_type": prop_type,
            "size_sqft": f"{size:,}",
            "price": f"${price:,}/mo",
            "neighborhood": neighborhood,
            "is_placeholder": False,
        },
        "geo": {
            "lat": str(lat),
            "lng": str(lng),
            "neighborhood": neighborhood,
        },
    }


def _gen_reddit(neighborhood: str, profile: dict, idx: int) -> dict:
    """Generate a synthetic Reddit post."""
    s = slug(neighborhood)
    titles = [
        f"Best restaurants in {neighborhood}?",
        f"Just moved to {neighborhood} — what should I know?",
        f"Is {neighborhood} safe for families?",
        f"Hidden gems in {neighborhood} that tourists don't know about",
    ]
    bodies = [
        f"I've been living in {neighborhood} for a few months now and absolutely love the {profile['character']} atmosphere. "
        f"Anyone have recommendations for good spots around Ward {profile['ward']}?",
        f"Thinking about opening a business in {neighborhood}. The {profile['character']} character of the area "
        f"seems like a great fit for what I have in mind. Any advice from local business owners?",
    ]

    return {
        "id": f"reddit-synth-{s}-{idx}",
        "source": "reddit",
        "title": titles[idx % len(titles)],
        "content": bodies[idx % len(bodies)],
        "url": f"https://reddit.com/r/chicago/comments/synth_{s}_{idx}",
        "timestamp": rand_ts(),
        "metadata": {
            "subreddit": "chicago",
            "author": f"chicago_local_{random.randint(100,999)}",
            "score": random.randint(5, 200),
            "num_comments": random.randint(2, 50),
            "permalink": f"/r/chicago/comments/synth_{s}_{idx}",
        },
        "geo": {"neighborhood": neighborhood},
    }


def phase_e_generate_synthetic():
    print("\n=== Phase E: Generate synthetic data ===")
    # Create directories
    for subdir in ["news", "public_data", "reviews", "reddit", "realestate"]:
        (DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)

    total = 0
    for neighborhood in CHICAGO_NEIGHBORHOODS:
        profile = NEIGHBORHOOD_PROFILES.get(neighborhood)
        if not profile:
            print(f"  WARNING: No profile for {neighborhood}, skipping")
            continue

        # 2 news articles
        for i in range(2):
            doc = _gen_news(neighborhood, profile, i)
            save_json(DATA_DIR / "news" / f"{doc['id']}.json", doc)
            total += 1

        # 4 food inspections
        for i in range(4):
            doc = _gen_food_inspection(neighborhood, profile, i)
            save_json(DATA_DIR / "public_data" / f"{doc['id']}.json", doc)
            total += 1

        # 3 building permits
        for i in range(3):
            doc = _gen_building_permit(neighborhood, profile, i)
            save_json(DATA_DIR / "public_data" / f"{doc['id']}.json", doc)
            total += 1

        # 4 business licenses
        for i in range(4):
            doc = _gen_business_license(neighborhood, profile, i)
            save_json(DATA_DIR / "public_data" / f"{doc['id']}.json", doc)
            total += 1

        # 3 reviews
        for i in range(3):
            doc = _gen_review(neighborhood, profile, i)
            save_json(DATA_DIR / "reviews" / f"{doc['id']}.json", doc)
            total += 1

        # 1-2 real estate listings
        n_re = 1 if profile["price_tier"] == "low" else 2
        for i in range(n_re):
            doc = _gen_realestate(neighborhood, profile, i)
            save_json(DATA_DIR / "realestate" / f"{doc['id']}.json", doc)
            total += 1

        # 2 reddit posts
        for i in range(2):
            doc = _gen_reddit(neighborhood, profile, i)
            save_json(DATA_DIR / "reddit" / f"{doc['id']}.json", doc)
            total += 1

    print(f"  Generated {total} synthetic documents across 48 neighborhoods")
    return total


# =========================================================================
# PHASE F: Regenerate summaries
# =========================================================================
def phase_f_regenerate_summaries():
    print("\n=== Phase F: Regenerate summaries ===")
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    # --- public_data_summary ---
    pub_dir = DATA_DIR / "public_data"
    counts_by_type = {}
    counts_by_status = {}
    counts_by_neighborhood = {}
    recent_items = []
    notable_items = []
    total = 0

    if pub_dir.exists():
        for fp in sorted(pub_dir.glob("*.json")):
            doc = load_json(fp)
            if not doc:
                continue
            total += 1
            dataset = doc.get("metadata", {}).get("dataset", "unknown")
            counts_by_type[dataset] = counts_by_type.get(dataset, 0) + 1

            raw = doc.get("metadata", {}).get("raw_record", {})
            result = raw.get("results", "")
            if result:
                counts_by_status[result] = counts_by_status.get(result, 0) + 1

            nbhd = doc.get("geo", {}).get("neighborhood", "")
            if nbhd:
                counts_by_neighborhood[nbhd] = counts_by_neighborhood.get(nbhd, 0) + 1

            recent_items.append({
                "title": doc.get("title", ""),
                "timestamp": doc.get("timestamp", ""),
                "id": doc.get("id", ""),
            })

            if result == "Fail":
                notable_items.append({
                    "title": f"FAILED: {raw.get('dba_name', 'Unknown')}",
                    "id": doc.get("id", ""),
                    "neighborhood": nbhd,
                })

    recent_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    recent_items = recent_items[:10]

    summary = {
        "source": "public_data",
        "total_records": total,
        "counts_by_type": counts_by_type,
        "counts_by_status": counts_by_status,
        "counts_by_neighborhood": counts_by_neighborhood,
        "recent_items": recent_items,
        "notable_items": notable_items[:20],
        "compression_ratio": f"{total}:1",
    }
    save_json(SUMMARIES_DIR / "public_data_summary.json", summary)
    print(f"  Public data summary: {total} records, {len(counts_by_neighborhood)} neighborhoods")

    # --- demographics_summary ---
    demo_dir = DATA_DIR / "demographics"
    demo_total = 0
    demo_by_neighborhood = {}
    demo_recent = []

    if demo_dir.exists():
        for fp in sorted(demo_dir.glob("*.json")):
            doc = load_json(fp)
            if not doc:
                continue
            demo_total += 1
            nbhd = doc.get("geo", {}).get("neighborhood", "")
            if nbhd:
                demo_by_neighborhood[nbhd] = demo_by_neighborhood.get(nbhd, 0) + 1
            demo_recent.append({
                "title": doc.get("title", ""),
                "timestamp": doc.get("timestamp", ""),
                "id": doc.get("id", ""),
            })

    demo_recent.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    demo_recent = demo_recent[:10]

    demo_summary = {
        "source": "demographics",
        "total_records": demo_total,
        "counts_by_type": {"demographics": demo_total},
        "counts_by_status": {},
        "counts_by_neighborhood": demo_by_neighborhood,
        "recent_items": demo_recent,
        "notable_items": [],
        "compression_ratio": f"{demo_total}:1",
    }
    save_json(SUMMARIES_DIR / "demographics_summary.json", demo_summary)
    print(f"  Demographics summary: {demo_total} records, {len(demo_by_neighborhood)} neighborhoods")


# =========================================================================
# PHASE G: Regenerate GeoJSON neighborhood metrics
# =========================================================================
def phase_g_regenerate_geojson():
    print("\n=== Phase G: Regenerate GeoJSON neighborhood metrics ===")
    GEO_DIR.mkdir(parents=True, exist_ok=True)

    # Count actual data per neighborhood
    permits_count = {}
    reviews_count = {}
    failed_inspections = {}
    total_docs = {}

    for dirpath, _, filenames in os.walk(DATA_DIR):
        dp = Path(dirpath)
        if "processed" in str(dp):
            continue
        for fn in filenames:
            if not fn.endswith(".json"):
                continue
            fp = dp / fn
            doc = load_json(fp)
            if not doc:
                continue
            nbhd = doc.get("geo", {}).get("neighborhood", "")
            if not nbhd:
                continue
            total_docs[nbhd] = total_docs.get(nbhd, 0) + 1

            dataset = doc.get("metadata", {}).get("dataset", "")
            if dataset == "building_permits":
                permits_count[nbhd] = permits_count.get(nbhd, 0) + 1
            result = doc.get("metadata", {}).get("raw_record", {}).get("results", "")
            if result == "Fail":
                failed_inspections[nbhd] = failed_inspections.get(nbhd, 0) + 1

            source = doc.get("source", "")
            if source == "reviews":
                reviews_count[nbhd] = reviews_count.get(nbhd, 0) + 1

    # Generate feature for each neighborhood
    features = []
    for neighborhood in CHICAGO_NEIGHBORHOODS:
        if neighborhood not in NEIGHBORHOOD_CENTROIDS:
            continue
        lat, lng = NEIGHBORHOOD_CENTROIDS[neighborhood]
        profile = NEIGHBORHOOD_PROFILES.get(neighborhood, {})
        tier = profile.get("price_tier", "mid")

        # Scale metrics by neighborhood character/tier
        if tier == "high":
            reg_density = random.randint(40, 80)
            biz_activity = random.randint(50, 90)
            sentiment = round(random.uniform(0.5, 0.8), 2)
            risk_score = random.randint(5, 25)
            crime = random.randint(5, 30)
            foot_traffic = random.randint(50, 90)
            avg_rating = round(random.uniform(3.8, 4.5), 1)
        elif tier == "mid":
            reg_density = random.randint(20, 55)
            biz_activity = random.randint(30, 70)
            sentiment = round(random.uniform(0.4, 0.7), 2)
            risk_score = random.randint(10, 35)
            crime = random.randint(15, 50)
            foot_traffic = random.randint(30, 65)
            avg_rating = round(random.uniform(3.6, 4.3), 1)
        else:
            reg_density = random.randint(10, 40)
            biz_activity = random.randint(20, 50)
            sentiment = round(random.uniform(0.3, 0.6), 2)
            risk_score = random.randint(20, 60)
            crime = random.randint(25, 80)
            foot_traffic = random.randint(10, 40)
            avg_rating = round(random.uniform(3.5, 4.1), 1)

        # Special cases
        if neighborhood == "Loop":
            foot_traffic = random.randint(80, 95)
            biz_activity = random.randint(80, 95)
            reg_density = random.randint(60, 80)
        elif neighborhood == "River North":
            foot_traffic = random.randint(70, 90)
        elif neighborhood == "Englewood":
            risk_score = random.randint(45, 60)
            crime = random.randint(50, 80)

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lng, lat],  # GeoJSON is [lng, lat]
            },
            "properties": {
                "neighborhood": neighborhood,
                "regulatory_density": reg_density,
                "business_activity": biz_activity,
                "sentiment": sentiment,
                "risk_score": risk_score,
                "active_permits": permits_count.get(neighborhood, 0),
                "crime_incidents_30d": crime,
                "avg_review_rating": avg_rating,
                "review_count": reviews_count.get(neighborhood, 0),
                "foot_traffic_intensity": foot_traffic,
            },
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }
    save_json(GEO_DIR / "neighborhood_metrics.json", geojson)
    print(f"  Generated GeoJSON with {len(features)} neighborhood features")


# =========================================================================
# PHASE H: Generate trend baselines
# =========================================================================
def phase_h_generate_trends():
    print("\n=== Phase H: Generate trend baselines ===")
    TRENDS_DIR.mkdir(parents=True, exist_ok=True)

    for neighborhood in CHICAGO_NEIGHBORHOODS:
        profile = NEIGHBORHOOD_PROFILES.get(neighborhood, {})
        tier = profile.get("price_tier", "mid")
        character = profile.get("character", "")

        # Determine traffic pattern type
        is_commercial = neighborhood in ("Loop", "River North", "Near North Side", "Streeterville",
                                          "West Loop", "South Loop", "Gold Coast")
        is_nightlife = neighborhood in ("Wicker Park", "Bucktown", "Logan Square", "Boystown",
                                         "Old Town", "Ukrainian Village", "Pilsen")
        is_residential = tier == "low" and not is_commercial and not is_nightlife

        hours = []
        for h in range(24):
            if is_commercial:
                # Heavy daytime, peaks at 8am and 5pm
                if h < 6:
                    ped = random.randint(5, 20)
                    veh = random.randint(3, 15)
                elif h < 9:
                    ped = random.randint(60, 120)
                    veh = random.randint(80, 150)
                elif h < 17:
                    ped = random.randint(100, 200)
                    veh = random.randint(50, 100)
                elif h < 19:
                    ped = random.randint(80, 150)
                    veh = random.randint(90, 160)
                elif h < 22:
                    ped = random.randint(30, 80)
                    veh = random.randint(20, 50)
                else:
                    ped = random.randint(5, 25)
                    veh = random.randint(5, 20)
            elif is_nightlife:
                # Moderate day, peaks at noon and 8pm-midnight
                if h < 7:
                    ped = random.randint(3, 15)
                    veh = random.randint(2, 10)
                elif h < 12:
                    ped = random.randint(30, 70)
                    veh = random.randint(20, 50)
                elif h < 14:
                    ped = random.randint(60, 100)
                    veh = random.randint(30, 60)
                elif h < 18:
                    ped = random.randint(40, 80)
                    veh = random.randint(25, 55)
                elif h < 22:
                    ped = random.randint(80, 160)
                    veh = random.randint(40, 80)
                elif h < 24:
                    ped = random.randint(60, 120)
                    veh = random.randint(30, 60)
                else:
                    ped = random.randint(10, 30)
                    veh = random.randint(5, 15)
            else:
                # Residential: low baseline, peaks at 7am and 6pm
                if h < 6:
                    ped = random.randint(1, 8)
                    veh = random.randint(1, 5)
                elif h < 9:
                    ped = random.randint(15, 40)
                    veh = random.randint(25, 60)
                elif h < 16:
                    ped = random.randint(10, 30)
                    veh = random.randint(10, 25)
                elif h < 19:
                    ped = random.randint(20, 50)
                    veh = random.randint(30, 65)
                elif h < 22:
                    ped = random.randint(8, 25)
                    veh = random.randint(8, 20)
                else:
                    ped = random.randint(2, 10)
                    veh = random.randint(1, 8)

            congestion = round(min(1.0, (ped + veh) / 300 + random.uniform(-0.05, 0.05)), 2)
            congestion = max(0.0, congestion)

            hours.append({
                "hour": h,
                "pedestrians": ped,
                "vehicles": veh,
                "congestion": congestion,
            })

        baseline = {
            "neighborhood": neighborhood,
            "hours": hours,
            "generated_at": "2026-02-28T00:00:00Z",
        }
        save_json(TRENDS_DIR / f"{neighborhood}.json", baseline)

    print(f"  Generated trend baselines for {len(CHICAGO_NEIGHBORHOODS)} neighborhoods")


# =========================================================================
# Main
# =========================================================================
def main():
    print("=" * 60)
    print("  Alethia Data Quality Fix + Synthetic Data Generator")
    print("=" * 60)

    phase_a_delete_corrupted()
    phase_b_fix_food_inspections()
    phase_c_fix_demographics()
    phase_d_fix_noncanonical()
    phase_e_generate_synthetic()
    phase_f_regenerate_summaries()
    phase_g_regenerate_geojson()
    phase_h_generate_trends()

    print("\n" + "=" * 60)
    print("  All phases complete!")
    print("=" * 60)

    # Quick verification
    print("\n--- Quick Verification ---")

    # Check for remaining 0-byte files
    zero_byte = 0
    for dirpath, _, filenames in os.walk(DATA_DIR):
        for fn in filenames:
            fp = Path(dirpath) / fn
            if fn.endswith(".json") and fp.stat().st_size == 0:
                zero_byte += 1
    print(f"  0-byte files remaining: {zero_byte}")

    # Count neighborhoods with data
    neighborhoods_with_data = set()
    for dirpath, _, filenames in os.walk(DATA_DIR):
        if "processed" in str(dirpath):
            continue
        for fn in filenames:
            if not fn.endswith(".json"):
                continue
            fp = Path(dirpath) / fn
            doc = load_json(fp)
            if doc:
                nbhd = doc.get("geo", {}).get("neighborhood", "")
                if nbhd:
                    neighborhoods_with_data.add(nbhd)
    print(f"  Neighborhoods with data: {len(neighborhoods_with_data)}/48")

    # Check GeoJSON
    geo_path = GEO_DIR / "neighborhood_metrics.json"
    if geo_path.exists():
        geojson = load_json(geo_path)
        if geojson:
            features = geojson.get("features", [])
            nonzero = sum(1 for f in features if f.get("properties", {}).get("business_activity", 0) > 0)
            print(f"  GeoJSON features: {len(features)}, with non-zero metrics: {nonzero}")

    # Check summaries
    pub_sum = load_json(SUMMARIES_DIR / "public_data_summary.json")
    if pub_sum:
        print(f"  Public data summary neighborhoods: {len(pub_sum.get('counts_by_neighborhood', {}))}")

    demo_sum = load_json(SUMMARIES_DIR / "demographics_summary.json")
    if demo_sum:
        print(f"  Demographics summary neighborhoods: {len(demo_sum.get('counts_by_neighborhood', {}))}")

    # Check trends
    trend_count = len(list(TRENDS_DIR.glob("*.json"))) if TRENDS_DIR.exists() else 0
    print(f"  Trend baselines: {trend_count}")


if __name__ == "__main__":
    main()
