import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.main import create_app

ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture
def client() -> Iterator[TestClient]:
    def add_test_routes(api: FastAPI) -> None:
        @api.get("/api/v1/__test/validation")
        async def test_validation(value: int) -> dict[str, int]:
            return {"value": value}

        @api.get("/api/v1/__test/unhandled")
        async def test_unhandled() -> None:
            raise RuntimeError("private-secret-detail")

        @api.get("/api/v1/__test/unhandled-sensitive")
        async def test_unhandled_sensitive(request: Request) -> None:
            query_secret = request.query_params["secret"]
            authorization = request.headers["Authorization"]
            raise RuntimeError(
                f"private-exception-secret {query_secret} {authorization}"
            )

    test_app = create_app(configure_api=add_test_routes)
    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        yield test_client


def assert_error_envelope(
    response, *, status_code: int, code: str
) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert "details" in body["error"]
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_health_contract(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "travelmate-api",
    }
    assert response.headers["X-Request-ID"]


def test_404_uses_error_envelope_and_request_id(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/not-found")

    assert_error_envelope(response, status_code=404, code="NOT_FOUND")


def test_422_uses_error_envelope_and_request_id(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/__test/validation")

    assert_error_envelope(
        response, status_code=422, code="VALIDATION_ERROR"
    )


def test_unhandled_500_has_request_id_cors_and_safe_logging(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    request_logger = logging.getLogger("travelmate.request")
    request_logger.addHandler(caplog.handler)
    try:
        response = client.get(
            "/api/v1/__test/unhandled",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Authorization": "Bearer test-secret-token",
            },
        )
    finally:
        request_logger.removeHandler(caplog.handler)

    assert_error_envelope(response, status_code=500, code="INTERNAL_ERROR")
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    logs = caplog.text
    assert "private-secret-detail" not in response.text
    assert "test-secret-token" not in logs
    assert "Authorization" not in logs
    assert "method=GET" in logs
    assert "path=/api/v1/__test/unhandled" in logs
    assert "status=500" in logs
    assert "duration_ms=" in logs
    assert f"request_id={response.headers['X-Request-ID']}" in logs


def test_500_does_not_log_exception_query_or_authorization_secrets(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    request_logger = logging.getLogger("travelmate.request")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    request_logger.addHandler(caplog.handler)
    uvicorn_error_logger.addHandler(caplog.handler)

    query_secret = "fake-query-secret"
    exception_secret = "private-exception-secret"
    authorization_secret = "fake-authorization-secret"

    try:
        response = client.get(
            f"/api/v1/__test/unhandled-sensitive?secret={query_secret}",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Authorization": f"Bearer {authorization_secret}",
            },
        )

        # Uvicorn logs unhandled ASGI exceptions with exc_info. Simulate that
        # record to verify the configured uvicorn.error filter drops its traceback.
        try:
            raise RuntimeError(
                f"simulated Uvicorn traceback containing {exception_secret}"
            )
        except RuntimeError:
            uvicorn_error_logger.exception("Exception in ASGI application")
    finally:
        request_logger.removeHandler(caplog.handler)
        uvicorn_error_logger.removeHandler(caplog.handler)

    assert_error_envelope(response, status_code=500, code="INTERNAL_ERROR")
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    logs = caplog.text

    assert "fake-query-secret" not in response.text
    assert "private-exception-secret" not in response.text
    assert "fake-authorization-secret" not in response.text
    assert query_secret not in logs
    assert exception_secret not in logs
    assert authorization_secret not in logs
    assert "Bearer " not in logs
    assert "Authorization" not in logs
    assert "method=GET" in logs
    assert "path=/api/v1/__test/unhandled-sensitive" in logs
    assert "status=500" in logs
    assert "duration_ms=" in logs
    assert f"request_id={response.headers['X-Request-ID']}" in logs
