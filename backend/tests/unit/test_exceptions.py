"""Exception handler and error-response tests."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    register_exception_handlers,
    to_error_response,
)


def test_to_error_response_shape():
    error = AppError("boom", status_code=418, code="teapot")
    response = to_error_response(error)

    assert response.status_code == 418
    import json

    body = json.loads(response.body)
    assert body == {"error": {"code": "teapot", "message": "boom"}}


def test_not_found_error():
    error = NotFoundError("Widget #3 not found.")
    assert error.status_code == 404
    assert error.code == "not_found"
    response = to_error_response(error)
    import json

    body = json.loads(response.body)
    assert body["error"]["code"] == "not_found"


def test_conflict_error():
    error = ConflictError("Already reviewed.")
    assert error.status_code == 409
    assert error.code == "conflict"


class TestClientExceptionHandlers:
    @pytest.fixture()
    def error_app(self):
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/boom")
        def boom():
            raise AppError("kapow", status_code=418, code="teapot")

        @app.get("/not-found")
        def not_found():
            raise NotFoundError("missing")

        return app

    def test_app_error_returns_json(self, error_app):
        with TestClient(error_app) as client:
            resp = client.get("/boom")
        assert resp.status_code == 418
        assert resp.json() == {"error": {"code": "teapot", "message": "kapow"}}

    def test_not_found_returns_json(self, error_app):
        with TestClient(error_app) as client:
            resp = client.get("/not-found")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_unknown_route_returns_http_error(self, error_app):
        with TestClient(error_app) as client:
            resp = client.get("/no-such-route")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "http_error"

    def test_validation_error_returns_422(self, error_app):
        @error_app.post("/validate")
        def validate(x: int):
            return {}

        with TestClient(error_app) as client:
            resp = client.post("/validate")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        assert "details" in body["error"]