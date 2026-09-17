from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import text
from app.production_db import SessionLocal
from app.production_api import router
from app.api_docs import router as system_router
from app.setup_api import router as setup_router
from app.bank_grade_api import router as bank_grade_router
from app.bank_grade_controls import router as controls_router
from app.bank_grade_middleware import bank_grade_security
from app.security import request_size_guard, allowed_origins
from app.payment_adapters import adapter_catalog

app = FastAPI(title="African Financial Trust Trust Engine", version="2.4.1", description="Production verification infrastructure for African commercial transactions.", docs_url="/docs", redoc_url="/redoc")
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

DASHBOARD = Path(__file__).with_name("dashboard_exact.html")
LEGACY_DASHBOARD = Path(__file__).with_name("dashboard_v2.html")

MOBILE_CSS = r'''
<style>
@media (max-width: 700px) {
  html, body { min-width: 0 !important; width: 100%; overflow-x: hidden; }
  body { font-size: 13px; }
  .app { min-width: 0; width: 100%; }
  .topbar { height: auto; min-height: 64px; padding: 10px 12px; flex-wrap: wrap; gap: 9px 12px; }
  .brand { width: auto; flex: 1 1 185px; min-width: 0; gap: 8px; }
  .brandmark { width: 34px; height: 34px; }
  .brandname { font-size: 10px; }
  .product { order: 3; width: 100%; border-left: 0; border-top: 1px solid #12354c; padding: 7px 0 0 42px; font-size: 10px; }
  .topright { margin-left: 0; gap: 9px; flex: 0 0 auto; }
  .online, .updated { display: none; }
  .profile { border-left: 0; padding-left: 0; }
  .avatar { width: 30px; height: 30px; }
  .ptext b { font-size: 9px; }
  .ptext small { font-size: 7px; }
  .shell { display: block; min-height: 0; }
  .sidebar { position: static; height: auto; width: 100%; overflow-x: auto; display: flex; align-items: center; gap: 4px; padding: 8px 10px; border-right: 0; border-bottom: 1px solid #10374f; white-space: nowrap; scrollbar-width: none; }
  .sidebar::-webkit-scrollbar { display: none; }
  .nav { flex: 0 0 auto; height: 34px; margin: 0; padding: 0 10px; font-size: 9px; }
  .nav .ico { width: 13px; }
  .sidebottom { display: none; }
  .main { padding: 18px 12px 28px; width: 100%; }
  .hero { display: block; margin-bottom: 15px; }
  .hero h1 { font-size: 22px; line-height: 1.15; }
  .hero p { font-size: 10px; margin-top: 5px; }
  .hero-right { text-align: left; margin-top: 10px; }
  .status { padding: 7px 11px; font-size: 9px; }
  .hero-right .updated { display: block; margin-top: 5px !important; font-size: 8px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
  .metric { height: 92px; padding: 12px; }
  .mlabel { font-size: 8px; }
  .mvalue { font-size: 24px; }
  .delta { font-size: 8px; }
  .content { display: block; }
  .card { margin-bottom: 12px; border-radius: 7px; }
  .chead { height: 43px; padding: 0 12px; }
  .chead h2 { font-size: 11px; }
  .cbody { padding: 12px; }
  .outcome { grid-template-columns: 1fr 1fr; min-height: 155px; gap: 7px; }
  .donut { width: 112px; height: 112px; }
  .donut:before { width: 82px; height: 82px; }
  .donuttext strong { font-size: 20px; }
  .donuttext small { font-size: 8px; }
  .legend { gap: 12px; }
  .legendrow { gap: 6px; grid-template-columns: 8px 1fr; }
  .legendrow small { grid-column: 2; font-size: 8px; }
  .legendrow b { font-size: 9px; }
  .table { min-width: 610px; }
  #transactions > div:last-child { overflow-x: auto; -webkit-overflow-scrolling: touch; }
}
@media (max-width: 390px) {
  .brandname { font-size: 9px; }
  .ptext { display: none; }
  .metrics { gap: 6px; }
  .metric { padding: 10px; }
  .mvalue { font-size: 21px; }
  .delta { font-size: 7px; }
  .outcome { grid-template-columns: 105px 1fr; }
  .donut { width: 100px; height: 100px; }
  .donut:before { width: 74px; height: 74px; }
}
</style>
'''

def dashboard_response():
    html = DASHBOARD.read_text(encoding="utf-8")
    html = html.replace('content="width=1440"', 'content="width=device-width, initial-scale=1, viewport-fit=cover"')
    html = html.replace("</head>", MOBILE_CSS + "</head>")
    return HTMLResponse(content=html, media_type="text/html")

@app.get("/", include_in_schema=False)
def root_dashboard():
    return dashboard_response()

@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "trust-engine", "version": "2.4.1", "database": "ok"}
    finally:
        db.close()

@app.get("/v1/payment-adapters")
def payment_adapters():
    return {"count": len(adapter_catalog()), "adapters": adapter_catalog()}

@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return dashboard_response()

@app.get("/legacy-dashboard", include_in_schema=False)
def legacy_dashboard():
    return FileResponse(LEGACY_DASHBOARD, media_type="text/html")
