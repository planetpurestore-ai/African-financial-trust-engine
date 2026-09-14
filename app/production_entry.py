from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import text
from app.production_db import init_production_db, SessionLocal
from app.production_api import router
from app.api_docs import router as system_router

init_production_db()

app = FastAPI(
    title="African Financial Trust — Trust Engine",
    version="2.2.0",
    description="Production verification infrastructure for African commercial transactions.",
)
app.include_router(system_router)
app.include_router(router)

@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "trust-engine", "version": "2.2.0", "database": "ok"}
    finally:
        db.close()

@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).with_name("dashboard.html"))
