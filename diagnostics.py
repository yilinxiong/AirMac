"""Sanitized in-memory runtime diagnostics."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Mapping

from airmac_version import AIRMAC_VERSION
from protocol import PROTOCOL_VERSION

QUEUE_METRIC_NAMES = {
    "pointer_depth",
    "pointer_high_water",
    "pointer_merged",
    "pointer_dropped",
    "pointer_expired",
    "control_depth",
    "control_high_water",
    "control_dropped",
}


@dataclass(slots=True)
class RuntimeDiagnostics:
    started_at: float = field(default_factory=time.monotonic)
    max_event_loop_lag_seconds: float = 0.0

    def record_event_loop_lag(self, lag_seconds: float) -> None:
        self.max_event_loop_lag_seconds = max(
            self.max_event_loop_lag_seconds, lag_seconds
        )

    def snapshot(
        self,
        *,
        controller_connected: bool,
        queue_metrics: Mapping[str, int],
        last_disconnect_category: str | None,
    ) -> dict[str, object]:
        return {
            "status": "ok",
            "version": AIRMAC_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "uptime_seconds": max(0, int(time.monotonic() - self.started_at)),
            "controller": "connected" if controller_connected else "idle",
            "queue_metrics": {
                str(key): int(value)
                for key, value in queue_metrics.items()
                if key in QUEUE_METRIC_NAMES
            },
            "event_loop_max_lag_ms": round(
                self.max_event_loop_lag_seconds * 1000, 1
            ),
            "last_disconnect_category": last_disconnect_category,
        }
