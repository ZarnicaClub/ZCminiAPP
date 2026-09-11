#!/usr/bin/env python3
"""Локальная проверка CRM-эндпоинтов (TestClient) против реальной БД."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from crm.app import app

client = TestClient(app)

for path in ["/", "/static/app.js", "/static/style.css", "/healthz",
             "/api/orders?limit=3", "/api/clients?limit=3", "/api/calendar"]:
    r = client.get(path)
    body = r.text[:100].replace("\n", " ")
    print(f"GET {path} -> {r.status_code} | {body}")

r = client.get("/api/orders?limit=1")
if r.status_code == 200 and r.json()["orders"]:
    oid = r.json()["orders"][0]["order_id"]
    print(f"GET /api/orders/{oid} -> {client.get(f'/api/orders/{oid}').status_code}")
    rc = client.get(f"/api/orders/{oid}/calls")
    print(f"GET /api/orders/{oid}/calls -> {rc.status_code} | {rc.text[:100]}")
