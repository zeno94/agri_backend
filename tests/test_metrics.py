"""Prometheus 指标测试。"""

from __future__ import annotations


async def test_metrics_endpoint_exposes_http_metrics(client, seed_data, boss_headers):
    # 先制造一次普通请求，让 Counter 有序列
    await client.get("/api/v1/parts", headers=boss_headers)

    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    text = response.text
    assert "erp_http_requests_total" in text
    assert 'route="/api/v1/parts"' in text


async def test_metrics_records_business_events(client, seed_data, boss_headers):
    await client.post(
        "/api/v1/sales/outbound",
        json={
            "customer_id": seed_data["customer_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 1}],
        },
        headers=boss_headers,
    )

    text = (await client.get("/metrics")).text
    assert "erp_business_events_total" in text
    assert 'event="sale.outbound"' in text


async def test_metrics_counts_idempotent_replay(client, seed_data, boss_headers):
    headers = {**boss_headers, "Idempotency-Key": "metrics-replay-0001"}
    payload = {
        "customer_id": seed_data["customer_id"],
        "items": [{"part_id": seed_data["part_id"], "quantity": 1}],
    }
    await client.post("/api/v1/sales/outbound", json=payload, headers=headers)
    await client.post("/api/v1/sales/outbound", json=payload, headers=headers)

    text = (await client.get("/metrics")).text
    assert 'event="idempotent.replay"' in text


async def test_metrics_exposes_dependency_gauges(client):
    text = (await client.get("/metrics")).text
    assert "erp_database_up" in text
    assert "erp_redis_up" in text


async def test_metrics_not_in_openapi_schema(client):
    schema = (await client.get("/openapi.json")).json()
    assert "/metrics" not in schema["paths"]
