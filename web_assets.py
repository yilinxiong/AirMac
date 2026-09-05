"""Explicit public asset inventory; repository files are never mounted wholesale."""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
WEB_ASSETS = frozenset({
    "app.js", "i18n.js", "settings.js", "background.js", "credentials.js",
    "pairing.js", "connection.js", "projection.js", "gestures.js", "locale.js",
    "styles.css",
})
