"""Small HTTP client with retries, used to fetch the IRC logs."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import requests

LOG = logging.getLogger(__name__)


class HttpError(RuntimeError):
    """Raised when a request permanently fails."""

    def __init__(
        self, message: str, *, status: int | None = None, url: str | None = None
    ):
        super().__init__(message)
        self.status = status
        self.url = url


class HttpClient:
    """Tiny wrapper around :mod:`requests`.

    Retries on 429/5xx responses and connection errors, honouring
    ``Retry-After`` when present, and can throttle consecutive requests.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        backoff: float = 1.5,
        max_backoff: float = 20.0,
        min_interval: float = 0.0,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_backoff = max_backoff
        self.min_interval = min_interval
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            }
        )
        self._last_request: float | None = None

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- internals ---------------------------------------------------------
    def _throttle(self) -> None:
        if not self.min_interval or self._last_request is None:
            return
        remaining = self.min_interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def _delay(self, attempt: int, response: requests.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.max_backoff)
                except ValueError:
                    pass
        delay = self.backoff * (2**attempt)
        jitter = random.uniform(0, delay / 4)
        return min(delay + jitter, self.max_backoff)

    # -- public API --------------------------------------------------------
    def get(
        self,
        url: str,
        params: Any = None,
        *,
        allow_status: tuple[int, ...] = (),
    ) -> requests.Response:
        """GET ``url``, retrying transient failures.

        Status codes listed in ``allow_status`` are returned to the caller
        instead of being raised, which the log fetcher uses for 404s (a day
        without a log means the channel was quiet).
        """
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle()
            response: requests.Response | None = None
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                last_error = exc
                LOG.debug("request error for %s (attempt %d): %s", url, attempt + 1, exc)
            else:
                if response.status_code in allow_status:
                    return response
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    last_error = HttpError(
                        f"HTTP {response.status_code} from {url}",
                        status=response.status_code,
                        url=url,
                    )
                    LOG.debug("%s (attempt %d)", last_error, attempt + 1)
                elif response.status_code >= 400:
                    raise HttpError(
                        f"HTTP {response.status_code} from {url}: "
                        f"{response.text[:200]}",
                        status=response.status_code,
                        url=url,
                    )
                else:
                    return response
            finally:
                self._last_request = time.monotonic()

            if attempt < self.retries:
                delay = self._delay(attempt, response)
                LOG.debug("retrying %s in %.1fs", url, delay)
                time.sleep(delay)

        raise HttpError(
            f"GET {url} failed after {self.retries + 1} attempts: {last_error}",
            url=url,
        ) from last_error

    def get_text(
        self,
        url: str,
        params: Any = None,
        *,
        allow_status: tuple[int, ...] = (),
    ) -> str:
        response = self.get(url, params, allow_status=allow_status)
        response.raise_for_status()
        return response.text

    def get_json(self, url: str, params: Any = None) -> Any:
        response = self.get(url, params)
        try:
            return json.loads(response.text)
        except ValueError as exc:
            raise HttpError(
                f"invalid JSON from {response.url}: {exc}", url=response.url
            ) from exc
