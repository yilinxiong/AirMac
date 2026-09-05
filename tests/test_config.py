from __future__ import annotations

import pytest

from config import AirMacSettings
from diagnostics import RuntimeDiagnostics


def test_runtime_settings_keep_documented_defaults() -> None:
    settings = AirMacSettings.from_env({})
    assert settings.port == 8000
    assert settings.auth_timeout_seconds == 5
    assert settings.session_idle_timeout_seconds == 16
    assert settings.monitor_interval_seconds == 1
    assert settings.log_level == "INFO"
    assert not settings.debug


def test_runtime_settings_accept_valid_overrides() -> None:
    settings = AirMacSettings.from_env(
        {
            "AIRMAC_PORT": "8123",
            "AIRMAC_AUTH_TIMEOUT_SECONDS": "3.5",
            "AIRMAC_SESSION_IDLE_SECONDS": "24",
            "AIRMAC_MONITOR_INTERVAL_SECONDS": "0.25",
            "AIRMAC_LOG_LEVEL": "debug",
            "AIRMAC_DEBUG": "1",
        }
    )
    assert settings.port == 8123
    assert settings.auth_timeout_seconds == 3.5
    assert settings.session_idle_timeout_seconds == 24
    assert settings.monitor_interval_seconds == 0.25
    assert settings.log_level == "DEBUG"
    assert settings.debug
    assert settings.loopback_base_url == "http://127.0.0.1:8123"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AIRMAC_PORT", "0"),
        ("AIRMAC_PORT", "65536"),
        ("AIRMAC_PORT", "eight thousand"),
        ("AIRMAC_SESSION_IDLE_SECONDS", "0"),
        ("AIRMAC_LOG_LEVEL", "VERBOSE"),
        ("AIRMAC_DEBUG", "yes"),
    ],
)
def test_runtime_settings_reject_invalid_values(name: str, value: str) -> None:
    with pytest.raises(ValueError):
        AirMacSettings.from_env({name: value})


def test_runtime_diagnostics_whitelist_queue_metrics() -> None:
    diagnostics = RuntimeDiagnostics()
    payload = diagnostics.snapshot(
        controller_connected=False,
        queue_metrics={"pointer_depth": 2, "private_text": 99},
        last_disconnect_category=None,
    )
    assert payload["queue_metrics"] == {"pointer_depth": 2}
