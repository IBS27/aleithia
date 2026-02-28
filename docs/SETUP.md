# Alethia Setup Guide

## Prerequisites

- Python 3.11+
- [Modal CLI](https://modal.com/docs/guide) (`pip install modal`)
- Modal account with credits (redeem code: `VVN-YQS-E55` at modal.com/credits)

## 1. Modal Authentication

```bash
modal token set --token-id <your-id> --token-secret <your-secret>
```

## 2. Create Modal Secrets

All API keys are stored as a single Modal secret group:

```bash
modal secret create alethia-secrets \
  NEWSAPI_KEY=your_key \
  REDDIT_CLIENT_ID=your_id \
  REDDIT_CLIENT_SECRET=your_secret \
  YELP_API_KEY=your_key \
  GOOGLE_PLACES_API_KEY=your_key \
  SOCRATA_APP_TOKEN=your_token \
  CENSUS_API_KEY=your_key \
  OPENAI_API_KEY=your_key
```

**Note:** Most pipelines work without API keys (using public endpoints or fallback data), but keys improve rate limits and data quality.

## 3. API Key Sources

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | Optional — RSS feeds work without it |
| `REDDIT_CLIENT_ID` / `SECRET` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps/) | Optional — JSON fallback works |
| `YELP_API_KEY` | [yelp.com/developers](https://www.yelp.com/developers) | Optional |
| `GOOGLE_PLACES_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) | Optional |
| `SOCRATA_APP_TOKEN` | [data.cityofchicago.org](https://data.cityofchicago.org/profile/edit/developer_settings) | Optional — public access works |
| `CENSUS_API_KEY` | [census.gov/developers](https://api.census.gov/data/key_signup.html) | Optional — works without key |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) | Required for vision pipeline |

## 4. Run Pipelines

```bash
# Test individual pipelines
modal run modal_app/pipelines/news.py::news_ingester
modal run modal_app/pipelines/politics.py::politics_ingester
modal run modal_app/pipelines/reddit.py::reddit_ingester
modal run modal_app/pipelines/reviews.py::review_ingester
modal run modal_app/pipelines/public_data.py::public_data_ingester
modal run modal_app/pipelines/demographics.py::demographics_ingester
modal run modal_app/pipelines/realestate.py::realestate_ingester

# Run data compression
modal run modal_app/compress.py::compress_raw_data

# Vision pipeline (requires OpenAI key)
modal run modal_app/pipelines/vision.py --youtube-url "https://youtube.com/watch?v=..."

# Deploy all (starts scheduled cron jobs)
modal deploy modal_app/pipelines/news.py
modal deploy modal_app/pipelines/politics.py
modal deploy modal_app/pipelines/reddit.py
modal deploy modal_app/pipelines/reviews.py
modal deploy modal_app/pipelines/public_data.py
modal deploy modal_app/pipelines/demographics.py
modal deploy modal_app/pipelines/realestate.py
```

## 5. Verify Data

```bash
# Check volume contents
modal volume ls alethia-data /raw/

# Check processed summaries
modal volume ls alethia-data /processed/summaries/

# Check GeoJSON output
modal volume ls alethia-data /processed/geo/
```

## 6. Local Development

```bash
docker compose up
```

This starts the FastAPI backend (port 8000) and React frontend (port 5173).
