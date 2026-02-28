from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import modal_router, data_router

app = FastAPI(title="HackIllinois 2026 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(modal_router, prefix="/api/modal")
app.include_router(data_router, prefix="/api/data")


@app.get("/api/health")
def health():
    return {"status": "ok"}
