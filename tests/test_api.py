from ac_trace.annotations import ac
from demo_api.app import create_app


@ac("AC-4")
def test_healthcheck():
    app = create_app()
    app.testing = True

    with app.test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


@ac("AC-3")
def test_quote_endpoint_returns_breakdown():
    app = create_app()
    app.testing = True

    with app.test_client() as client:
        response = client.post(
            "/quote",
            json={"subtotal": 120, "is_vip": True, "expedited": True},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "subtotal": 120.0,
        "discount": 12.0,
        "shipping": 15.0,
        "total": 123.0,
    }
