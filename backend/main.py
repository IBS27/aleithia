from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import data_router
from routes.data_routes import prime_route_data_snapshots
from database import init_db

app = FastAPI(title="Aleithia API")

# Initialize database tables
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router, prefix="/api/data")


@app.on_event("startup")
def startup_route_snapshots():
    prime_route_data_snapshots()


@app.get("/api/health")
def health():
    return {"status": "ok"}
