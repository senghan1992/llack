"""Prometheus metrics.

A handful of series that answer the questions an operator actually asks of a
chat server: is it slow (`llack_http_request_seconds`), is it erroring
(`llack_http_requests_total{status}`), how many sockets are open
(`llack_ws_connections`), is anyone talking (`llack_messages_created_total`),
and are the background jobs alive (`llack_workers_runs_total`).

Request labels use the *route template* (`/api/v1/channels/{channel_id}`),
never the raw path — one label per ULID would grow the series set without
bound and make the metrics page itself the incident.
"""

from __future__ import annotations

from collections.abc import Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry()

http_requests_total = Counter(
    "llack_http_requests_total",
    "HTTP requests by method, route template and status code.",
    ["method", "path_template", "status"],
    registry=registry,
)
http_request_seconds = Histogram(
    "llack_http_request_seconds",
    "HTTP request latency by method and route template.",
    ["method", "path_template"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)
ws_connections = Gauge(
    "llack_ws_connections",
    "Open WebSocket connections on this process.",
    registry=registry,
)
messages_created_total = Counter(
    "llack_messages_created_total",
    "Messages accepted by POST /channels/{id}/messages.",
    registry=registry,
)
workers_runs_total = Counter(
    "llack_workers_runs_total",
    "Background worker iterations, by worker and outcome.",
    ["worker", "outcome"],
    registry=registry,
)


def bind_ws_gauge(read: Callable[[], int]) -> None:
    """Point the connection gauge at the hub's live count."""
    ws_connections.set_function(read)


def render() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST


def observe_request(method: str, path_template: str, status: int, seconds: float) -> None:
    http_requests_total.labels(method, path_template, str(status)).inc()
    http_request_seconds.labels(method, path_template).observe(seconds)
