"""Test that authentication is required for protected endpoints."""


def test_unauthenticated_request_requires_auth(unauthenticated_client):
    """Verify that requests without auth header get 401."""
    response = unauthenticated_client.get("/protocols")
    assert response.status_code == 401


def test_invalid_auth_header_returns_401(unauthenticated_client):
    """Verify that requests with invalid auth header get 401."""
    response = unauthenticated_client.get(
        "/protocols",
        headers={"Authorization": "Invalid token"},
    )
    assert response.status_code == 401
    assert "Missing or invalid auth header" in response.json()["detail"]


def test_authenticated_request_succeeds(test_client):
    """Verify that requests with auth override work."""
    response = test_client.get("/protocols")
    # Should not get 401 or 422 - may get 200 or other status depending on data
    assert response.status_code in [200, 404]  # 200 with data or 404 without
