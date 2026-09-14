from fastapi import FastAPI
from app.production_db import init_production_db
from app.production_api import router
from app.api_docs import router as system_router

init_production_db()

app = FastAPI(
    title="African Financial Trust — Trust Engine",
    version="2.1.0",
    description="Production verification infrastructure for African commercial transactions.",
)
app.include_router(system_router)
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "trust-engine", "version": "2.1.0", "database": "ok"}
