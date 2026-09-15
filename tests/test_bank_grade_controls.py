import os
os.environ["DATABASE_URL"]="sqlite:///./test_bank_grade.db"
os.environ["API_KEY_PEPPER"]="bank-grade-test-pepper"
os.environ["BOOTSTRAP_TOKEN"]="bank-grade-bootstrap"
from fastapi.testclient import TestClient
from app.production_entry import app
from app.production_db import Base, engine
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
client=TestClient(app)

def test_bank_grade_graph_and_key_controls(monkeypatch):
    # Keep the bootstrap secret deterministic even when the full suite imports
    # other modules that may manipulate process environment variables.
    monkeypatch.setenv("BOOTSTRAP_TOKEN", "bank-grade-bootstrap")
    monkeypatch.setenv("API_KEY_PEPPER", "bank-grade-test-pepper")
    r=client.post("/v1/organizations",headers={"X-Bootstrap-Token":"bank-grade-bootstrap"},json={"name":"Bank Grade Test"})
    assert r.status_code==201, r.text
    key=r.json()["api_key"]
    h={"X-API-Key":key}
    status=client.get("/v1/bank-grade/status",headers=h)
    assert status.status_code==200
    assert status.json()["capabilities"]["trust_graph"] is True
    a=client.post("/v1/bank-grade/entities",headers=h,json={"entity_type":"business","external_id":"RW-BIZ-001","name":"Seller Ltd","verified":True})
    b=client.post("/v1/bank-grade/entities",headers=h,json={"entity_type":"business","external_id":"RW-BIZ-002","name":"Buyer Ltd"})
    assert a.status_code==201 and b.status_code==201
    rel=client.post("/v1/bank-grade/relationships",headers=h,json={"source_entity_id":a.json()["entity_id"],"relationship_type":"sells_to","target_entity_id":b.json()["entity_id"],"confidence":98})
    assert rel.status_code==201
    graph=client.get(f"/v1/bank-grade/entities/{a.json()['entity_id']}/graph",headers=h)
    assert graph.status_code==200 and len(graph.json()["relationships"])==1
    keys=client.get("/v1/keys",headers=h)
    assert keys.status_code==200
    key_id=keys.json()["keys"][0]["id"]
    policy=client.post(f"/v1/bank-grade/controls/keys/{key_id}/policy",headers=h,json={"expires_in_days":30,"scopes":["transactions:read"]})
    assert policy.status_code==200
    denied=client.get("/v1/documents",headers=h)
    assert denied.status_code==403

def test_invalid_key_rejected():
    r=client.get("/v1/bank-grade/status",headers={"X-API-Key":"aft_live_invalid"})
    assert r.status_code==401
