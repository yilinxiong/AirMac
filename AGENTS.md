# AirMac Agent Guide

## Scope and goal

This file applies to the entire repository. AirMac is a personal open-source macOS
remote controller: an iPhone connects over a trusted local network and acts as a
trackpad, keyboard, clipboard bridge, and system-control surface.

Preserve the current low-friction HTTP/WS setup and existing UI unless the user
explicitly requests a breaking change. HTTP/WS provides authentication but not
transport confidentiality; never describe it as safe for an untrusted network.

## Supported environment

- Runtime target: Python 3.12, current macOS, primarily Apple Silicon.
- CI runs Python tests on macOS and Ubuntu. `tests/conftest.py` supplies Quartz and
  pynput stubs outside macOS.
- The native menu-bar manager is Objective-C/AppKit and builds with `clang`.
- The optional copy HUD is Swift. A Swift compiler/SDK mismatch is allowed to fall
  back to a macOS notification; it must not prevent service installation.
- The current macOS 26 application grid is `/System/Applications/Apps.app`.
  Older macOS versions use Launchpad, so retain both paths.

## Source map

- `main.py`: FastAPI composition, LAN/origin checks, pairing routes, WebSocket
  authentication, single-controller session ownership, revocation monitoring,
  health endpoint, and PWA assets.
- `auth.py`: pairing state and `DeviceStore`; token hashes, file locking, atomic
  replacement, permissions, expiry, rate limits, and dialog lifecycle.
- `protocol.py`: strict discriminated Pydantic message models and 64 KiB envelope
  limit. Add every new WebSocket action here first. `quick_action` accepts only
  its reviewed fixed enum; never turn it into a free-form command surface.
- `mac_controller.py`: bounded pointer/control queues, Quartz input, ordered system
  commands, clipboard serialization, wake assertion, and forced input release.
- `index.html`: mobile UI, pairing flow, WebSocket lifecycle, touch handling,
  keyboard input, text projection, and install hint.
- `frontend_state.js`: browser/Node-compatible state machines for reconnects,
  projection, gestures, preferences, and latency. Put isolated logic here and
  unit test it.
- `ui_components.js`: build-free native Web Components for the connection pill
  and Quick Deck. Keep deck messages fixed data, not user-provided commands.
- `menubar.m`: native AppKit status item. It invokes `manage_devices.py` through
  argv; do not duplicate or directly mutate the credential format.
- `manage_devices.py`: local CLI for list, revoke, clear, status, and diagnostics.
- `pairing_dialog.py`: fixed Cocoa dialog source. Device names are argv data, never
  interpolated into AppleScript or source strings.
- `install_service.sh` / `uninstall_service.sh`: LaunchAgent lifecycle.
- `manifest.webmanifest`, `service-worker.js`, `offline.html`, `icons/`: PWA shell.
- `tests/`: protocol, authentication, controller, WebSocket, CLI, frontend state,
  and queue stress coverage.

## Non-negotiable invariants

### Authentication and storage

- Pairing codes and bearer tokens come from `secrets`; clients never choose IDs or
  tokens.
- The WebSocket authenticates only through its first JSON frame. Never put tokens
  in a URL, query string, access log, notification, or exception message.
- Store only SHA-256 token digests and compare them in constant time.
- Keep the device directory at mode `700`, database/lock files at `600`, and write
  the database atomically under an exclusive lock.
- Continue rejecting non-LAN addresses and mismatched/missing WebSocket origins.
- Do not read, migrate, or delete legacy `whitelist.json` automatically.
- Revoking a device must disconnect its active session within roughly one second.

### Protocol and input safety

- Keep Pydantic models strict and extra fields forbidden. Reject unknown actions,
  wrong types, NaN/infinity, oversized text, and out-of-range motion.
- Keep the 64 KiB WebSocket message limit, move range `±500`, scroll range
  `±1000`, key text limit 16 characters, and projection limit 32 KiB UTF-8 unless
  a reviewed protocol change deliberately updates tests and documentation.
- Never block the asyncio event loop with Quartz, clipboard, AppleScript, process,
  or keyboard work. Use the existing executors/async subprocess helpers.
- Preserve bounded queues, pointer ordering, move/scroll coalescing, and stale
  pointer-event expiry.
- Clipboard-dependent operations remain serialized. Long-text projection restores
  the old clipboard only if the projected value is still present.
- Register work per connection and cancel it during reset. Every disconnect path,
  exception, replacement, and shutdown must release mouse buttons and modifiers.
- Only one device controls the Mac at a time. A same-device connection may replace
  its old session; a different active device receives `controller_busy`. A stale
  mobile session may expire after the current idle lease.

### Mobile lifecycle and gestures

- iPhone lock, backgrounding, page suspension, Wi-Fi changes, and reconnects are
  normal lifecycle events, not exceptional failures. Preserve backoff/jitter,
  heartbeats, idempotent authentication, and draft retention.
- Long-text requests keep one request ID across uncertain retries. Clear the field
  only after matching success/duplicate acknowledgement; keep it on failure.
- Record the maximum finger count for the full gesture and classify only after the
  final lift. A multi-finger gesture must not degrade into a lower-finger click or
  swipe while fingers are lifted one at a time.
- Three- and four-finger upward actions may be remapped through validated local
  preferences. Each must still trigger at most once per gesture. `app_launcher`
  opens Apps on macOS 26 and falls back to Launchpad on older macOS.
- The text clear control stays compact and inside the textarea so it does not take
  a separate mobile layout column.
- Pointer and scroll preference values must be normalized and client-generated
  motion must remain inside the server protocol bounds.

### Wake and PWA behavior

- Wake uses a managed, nonblocking `caffeinate -d -u -t 30` assertion and a delayed
  Shift key. It must not bypass the macOS lock screen or password policy.
- The assertion intentionally outlives a normal phone WebSocket disconnect for its
  bounded 30-second duration, but is stopped on service shutdown/replacement.
- Plain LAN HTTP may not support Service Workers. PWA registration must remain
  optional and must never block normal remote-control startup.
- When changing a frontend script, bump both its query version in `index.html`
  and `CACHE_NAME` in `service-worker.js`. Keep scripts network-first so an old
  worker cannot combine a new page with incompatible cached modules.
- Preserve the manifest, Apple touch icon, 192/512 icons, and maskable icon routes.
  Regenerate icons with `tools/generate_pwa_icons.sh` after source artwork changes.

## Working procedure

1. Start with `git status --short --branch`. Treat all pre-existing changes as user
   work and preserve them.
2. Read the relevant tests and neighboring implementation before editing.
3. Prefer small, typed, testable changes. Parameterize subprocesses; never use
   `os.system`, shell interpolation, or external-input source construction.
4. Add or update tests with behavior changes. Automated tests must mock physical
   mouse, keyboard, sleep, wake, clipboard, and GUI effects.
5. Run checks proportional to the change. For a normal full validation:

   ```bash
   venv/bin/python -m pytest -q
   node --test tests/frontend_state.test.js tests/ui_components.test.js
   venv/bin/python -m compileall -q main.py auth.py protocol.py mac_controller.py manage_devices.py pairing_dialog.py tests
   sed -n '/^[[:space:]]*<script>$/,/^[[:space:]]*<\/script>$/p' index.html | sed '1d;$d' | node --check -
   node --check service-worker.js
   venv/bin/python -m json.tool manifest.webmanifest >/dev/null
   bash -n install_service.sh uninstall_service.sh tools/generate_pwa_icons.sh
   venv/bin/python -m pip check
   clang -fobjc-arc -framework Cocoa menubar.m -o /tmp/airmac-menubar-check
   git diff --check
   ```

6. Browser layout changes should be checked at an iPhone-sized viewport when the
   available browser tooling permits it. Hardware gestures still require final
   Mac+iPhone manual verification.
7. Deploy Python/controller changes with `./install_service.sh` or a scoped
   `launchctl kickstart -k gui/$(id -u)/com.airmac.remote` only when authorized.
   Verify with `venv/bin/python manage_devices.py diagnose` and inspect logs.
8. Do not revoke/clear devices, delete logs/data, rewrite Git history, or remove the
   user's local `remote.log`/`whitelist.json` unless explicitly requested.

## Runtime paths and labels

- Server LaunchAgent: `com.airmac.remote`
- Menu-bar LaunchAgent: `com.airmac.remote.menubar`
- Default server: `http://0.0.0.0:8000` (phone uses the Mac's private LAN IP)
- Health check: `http://127.0.0.1:8000/api/health`
- Device store: `~/Library/Application Support/AirMac/authorized_devices.json`
- Runtime logging config: `~/Library/Application Support/AirMac/logging_config.json`
- Main log: `~/Library/Logs/AirMac/remote.log`
- Launcher log: `~/Library/Logs/AirMac/launcher.log`
- Menu-bar log: `~/Library/Logs/AirMac/menubar.log`

Never commit generated binaries (`hud`, `airmac-menubar`), virtual environments,
local logs, device stores, lock files, or pairing credentials.
