def _create_farm(client, headers, code="MLFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "ML Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_ml_yield_predict_matches_the_real_engine(client, tenant):
    headers = tenant.auth_headers(client)
    res = client.post(
        "/api/v1/ml/yield/predict",
        json={"tree_count": 10, "avg_fruit_count_per_tree": 20, "avg_fruit_weight_kg": 3.0},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    point = 10 * 20 * 3.0
    assert body["estimated_yield_kg_low"] == round(point * 0.8, 1)
    assert body["estimated_yield_kg_high"] == round(point * 1.2, 1)
    assert 0 < body["confidence"] <= 0.85


def test_ml_disease_predict(client, tenant):
    headers = tenant.auth_headers(client)
    res = client.post(
        "/api/v1/ml/disease/predict",
        json={"humidity_pct": 90, "rainfall_mm_7d": 30, "leaf_wetness_hours": 8, "recent_confirmed_incident_count": 2, "recent_vision_detection_confidence": 0.9},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["band"] == "critical"
    assert body["risk_score"] >= 75


def test_ml_irrigation_predict(client, tenant):
    headers = tenant.auth_headers(client)
    res = client.post(
        "/api/v1/ml/irrigation/predict",
        json={"soil_moisture_pct": 20, "target_moisture_pct": 35, "forecast_rain_mm": 0, "area_hectares": 2.0},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["should_irrigate"] is True
    assert body["recommended_volume_liters"] == 15 * 2.0 * 150.0


def test_ml_farm_score_predict_matches_get_endpoint(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="MLFARM1")

    ml_res = client.post("/api/v1/ml/farm-score/predict", json={"farm_id": farm["id"]}, headers=headers)
    assert ml_res.status_code == 200, ml_res.text
    ml_body = ml_res.json()

    get_res = client.get(f"/api/v1/ai/farms/{farm['id']}/score", headers=headers)
    get_body = get_res.json()

    assert ml_body["score"] == get_body["score"]
    assert ml_body["band"] == get_body["band"]


def test_ml_farm_score_predict_unknown_farm_returns_404(client, tenant):
    headers = tenant.auth_headers(client)
    res = client.post(
        "/api/v1/ml/farm-score/predict", json={"farm_id": "00000000-0000-0000-0000-000000000000"}, headers=headers
    )
    assert res.status_code == 404


def test_ml_predictions_are_recorded(client, tenant):
    headers = tenant.auth_headers(client)
    client.post(
        "/api/v1/ml/yield/predict",
        json={"tree_count": 5, "avg_fruit_count_per_tree": 10, "avg_fruit_weight_kg": 2.0},
        headers=headers,
    )
    predictions_res = client.get("/api/v1/ai/predictions", params={"entity_type": "ml_yield_query"}, headers=headers)
    assert predictions_res.status_code == 200
    assert len(predictions_res.json()) == 1
