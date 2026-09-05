from __future__ import annotations

import pytest

from config import AirMacSettings, load_local_settings
from diagnostics import RuntimeDiagnostics


def test_runtime_settings_keep_documented_defaults() -> None:
    settings = AirMacSettings.from_env({})
    assert settings.port == 8000
    assert settings.auth_timeout_seconds == 5
    assert settings.session_idle_timeout_seconds == 16
    assert settings.monitor_interval_seconds == 1
    assert settings.log_level == "INFO"
    assert not settings.debug
    assert settings.keep_reachable_on_ac


def test_runtime_settings_accept_valid_overrides() -> None:
    settings = AirMacSettings.from_env(
        {
            "AIRMAC_PORT": "8123",
            "AIRMAC_AUTH_TIMEOUT_SECONDS": "3.5",
            "AIRMAC_SESSION_IDLE_SECONDS": "24",
            "AIRMAC_MONITOR_INTERVAL_SECONDS": "0.25",
            "AIRMAC_LOG_LEVEL": "debug",
            "AIRMAC_DEBUG": "1",
            "AIRMAC_KEEP_REACHABLE_ON_AC": "0",
        }
    )
    assert settings.port == 8123
    assert settings.auth_timeout_seconds == 3.5
    assert settings.session_idle_timeout_seconds == 24
    assert settings.monitor_interval_seconds == 0.25
    assert settings.log_level == "DEBUG"
    assert settings.debug
    assert not settings.keep_reachable_on_ac
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
        ("AIRMAC_KEEP_REACHABLE_ON_AC", "always"),
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


def test_local_tools_use_installed_port_with_environment_override(tmp_path) -> None:
    settings_path = tmp_path / "runtime.json"
    settings_path.write_text(
        '{"port": 8123, "log_level": "WARNING", "keep_reachable_on_ac": false}'
    )
    installed = load_local_settings({}, settings_path)
    assert installed.port == 8123
    assert installed.log_level == "WARNING"
    assert not installed.keep_reachable_on_ac
    overridden = load_local_settings({"AIRMAC_PORT": "9000"}, settings_path)
    assert overridden.port == 9000
