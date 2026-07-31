from app import create_app


def test_health_endpoint_reports_ok():
    app = create_app("testing")

    with app.test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload
    assert payload.get("status") == "healthy"
