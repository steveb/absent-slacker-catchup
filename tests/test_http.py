"""Tests for the retrying HTTP client."""

from __future__ import annotations

import pytest
import responses

from asc.http import HttpClient, HttpError

URL = "https://example.com/page.html"


@pytest.fixture
def client(monkeypatch):
    # Keep the retry backoff out of the test runtime.
    sleeps: list[float] = []
    monkeypatch.setattr("asc.http.time.sleep", sleeps.append)
    http = HttpClient("asc/test", retries=2, backoff=0.01)
    yield http, sleeps
    http.close()


@responses.activate
def test_retries_transient_failures(client):
    http, sleeps = client
    responses.add(responses.GET, URL, status=500)
    responses.add(responses.GET, URL, body="recovered")

    assert http.get_text(URL) == "recovered"
    assert len(responses.calls) == 2
    assert sleeps


@responses.activate
def test_honours_retry_after(client):
    http, sleeps = client
    responses.add(responses.GET, URL, status=429, headers={"Retry-After": "2"})
    responses.add(responses.GET, URL, body="ok")

    assert http.get_text(URL) == "ok"
    assert 2.0 in sleeps


@responses.activate
def test_client_errors_are_not_retried(client):
    http, _ = client
    responses.add(responses.GET, URL, status=400, body="bad request")

    with pytest.raises(HttpError) as excinfo:
        http.get_text(URL)

    assert excinfo.value.status == 400
    assert len(responses.calls) == 1


@responses.activate
def test_allow_status_returns_the_response(client):
    http, _ = client
    responses.add(responses.GET, URL, status=404, body="")

    response = http.get(URL, allow_status=(404,))

    assert response.status_code == 404
    assert len(responses.calls) == 1


@responses.activate
def test_exhausted_retries_raise(client):
    http, _ = client
    for _ in range(3):
        responses.add(responses.GET, URL, status=503, body="")

    with pytest.raises(HttpError) as excinfo:
        http.get_text(URL)

    assert "failed after 3 attempts" in str(excinfo.value)
    assert len(responses.calls) == 3


@responses.activate
def test_get_json(client):
    http, _ = client
    responses.add(responses.GET, URL, json={"answer": 42})

    assert http.get_json(URL) == {"answer": 42}


@responses.activate
def test_invalid_json_raises(client):
    http, _ = client
    responses.add(responses.GET, URL, body="not json")

    with pytest.raises(HttpError):
        http.get_json(URL)


@responses.activate
def test_user_agent_is_sent(client):
    http, _ = client
    responses.add(responses.GET, URL, body="ok")

    http.get_text(URL)

    assert responses.calls[0].request.headers["User-Agent"] == "asc/test"
