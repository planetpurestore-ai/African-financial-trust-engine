from fastapi import FastAPI
from app.production_db import init_production_db
from app.production_api import router

init_production_db()

app = FastAPI(
    title="African Financial Trust — Trust Engine",
    version="2.0.0",
    description="Production verification infrastructure for African commercial transactions.",
)
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "trust-engine", "version": "2.0.0", "database": "ok"}
