"""Validated runtime configuration shared by AirMac entry points."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


RUNTIME_SETTINGS_PATH = (
    Path.home() / "Library" / "Application Support" / "AirMac" / "runtime.json"
)


def _integer(
    values: Mapping[str, str], name: str, default: int, minimum: int, maximum: int
) -> int:
    raw = values.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _seconds(
    values: Mapping[str, str], name: str, default: float, minimum: float, maximum: float
) -> float:
    raw = values.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


def _boolean(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or raw == "":
        return default
    if raw not in {"0", "1"}:
        raise ValueError(f"{name} must be 0 or 1")
    return raw == "1"


@dataclass(frozen=True, slots=True)
class AirMacSettings:
    port: int = 8000
    auth_timeout_seconds: float = 5.0
    session_idle_timeout_seconds: float = 16.0
    monitor_interval_seconds: float = 1.0
    metrics_log_interval_seconds: float = 30.0
    event_loop_lag_warning_seconds: float = 0.1
    log_level: str = "INFO"
    debug: bool = False
    keep_reachable_on_ac: bool = True

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AirMacSettings:
        values = os.environ if environ is None else environ
        log_level = values.get("AIRMAC_LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "AIRMAC_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
            )
        return cls(
            port=_integer(values, "AIRMAC_PORT", 8000, 1, 65_535),
            auth_timeout_seconds=_seconds(
                values, "AIRMAC_AUTH_TIMEOUT_SECONDS", 5.0, 0.1, 60.0
            ),
            session_idle_timeout_seconds=_seconds(
                values, "AIRMAC_SESSION_IDLE_SECONDS", 16.0, 1.0, 600.0
            ),
            monitor_interval_seconds=_seconds(
                values, "AIRMAC_MONITOR_INTERVAL_SECONDS", 1.0, 0.05, 60.0
            ),
            metrics_log_interval_seconds=_seconds(
                values, "AIRMAC_METRICS_LOG_INTERVAL_SECONDS", 30.0, 1.0, 3600.0
            ),
            event_loop_lag_warning_seconds=_seconds(
                values, "AIRMAC_EVENT_LOOP_LAG_WARNING_SECONDS", 0.1, 0.01, 10.0
            ),
            log_level=log_level,
            debug=_boolean(values, "AIRMAC_DEBUG", False),
            keep_reachable_on_ac=_boolean(
                values, "AIRMAC_KEEP_REACHABLE_ON_AC", True
            ),
        )

    @property
    def loopback_base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def load_local_settings(
    environ: Mapping[str, str] | None = None,
    path: Path = RUNTIME_SETTINGS_PATH,
) -> AirMacSettings:
    """Load installer-persisted settings, with explicit environment overrides."""

    values = dict(os.environ if environ is None else environ)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"unable to read AirMac runtime settings: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("AirMac runtime settings must contain a JSON object")
        for environment_name, key in (
            ("AIRMAC_PORT", "port"),
            ("AIRMAC_LOG_LEVEL", "log_level"),
            ("AIRMAC_KEEP_REACHABLE_ON_AC", "keep_reachable_on_ac"),
        ):
            if environment_name not in values and key in payload:
                stored_value = payload[key]
                if key == "keep_reachable_on_ac" and isinstance(stored_value, bool):
                    values[environment_name] = "1" if stored_value else "0"
                else:
                    values[environment_name] = str(stored_value)
    return AirMacSettings.from_env(values)
