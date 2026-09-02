from __future__ import annotations

from manage_devices import build_parser, parse_launchctl_output


def test_parse_launchctl_output() -> None:
    output = """
    com.airmac.remote = {
        state = running
        pid = 12345
    }
    """
    assert parse_launchctl_output(output) == ("running", "12345")
    assert parse_launchctl_output("no service") == ("unknown", "-")


def test_management_parser_includes_diagnostics() -> None:
    assert build_parser().parse_args(["status"]).command == "status"
    assert build_parser().parse_args(["diagnose"]).command == "diagnose"
