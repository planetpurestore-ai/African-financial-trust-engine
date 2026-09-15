from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text
from app.production_db import init_production_db, SessionLocal
from app.production_api import router
from app.api_docs import router as system_router
from app.setup_api import router as setup_router
from app.bank_grade_api import router as bank_grade_router
from app.bank_grade_controls import router as controls_router
from app.bank_grade_middleware import bank_grade_security
from app.security import request_size_guard, allowed_origins
from app.payment_adapters import adapter_catalog

init_production_db()
app = FastAPI(title="African Financial Trust Trust Engine", version="2.4.0", description="Production verification infrastructure for African commercial transactions.", docs_url="/docs", redoc_url="/redoc")
origins = allowed_origins()
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key", "X-Bootstrap-Token", "X-Organization-ID", "X-Webhook-Signature", "Idempotency-Key"])
app.middleware("http")(request_size_guard)
app.middleware("http")(bank_grade_security)
app.include_router(system_router)
app.include_router(router)
app.include_router(setup_router)
app.include_router(bank_grade_router)
app.include_router(controls_router)

@app.get("/", include_in_schema=False)
def root_dashboard():
    return FileResponse(Path(__file__).with_name("dashboard_v3.html"))

@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "trust-engine", "version": "2.4.0", "database": "ok"}
    finally:
        db.close()

@app.get("/v1/payment-adapters")
def payment_adapters():
    return {"count": len(adapter_catalog()), "adapters": adapter_catalog()}

@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).with_name("dashboard_v3.html"))

@app.get("/legacy-dashboard", include_in_schema=False)
def legacy_dashboard():
    return FileResponse(Path(__file__).with_name("dashboard_v2.html"))
