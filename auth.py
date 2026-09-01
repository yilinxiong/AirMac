from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fcntl


DEFAULT_DATA_DIR = Path.home() / "Library" / "Application Support" / "AirMac"
PAIRING_DIALOG_PATH = Path(__file__).with_name("pairing_dialog.py")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DeviceStoreError(RuntimeError):
    pass


class DeviceStore:
    """Atomic, process-safe storage for paired device token digests."""

    def __init__(self, path: Path | None = None) -> None:
        data_dir = Path(os.environ.get("AIRMAC_DATA_DIR", DEFAULT_DATA_DIR))
        self.path = path or data_dir / "authorized_devices.json"
        self.lock_path = self.path.with_suffix(".lock")

    def _ensure_directory(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)

    def _empty_data(self) -> dict[str, Any]:
        return {"version": 1, "devices": {}}

    def _read_unlocked(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._empty_data()
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            raise DeviceStoreError("无法读取已配对设备数据库") from exc
        if raw.get("version") != 1 or not isinstance(raw.get("devices"), dict):
            raise DeviceStoreError("已配对设备数据库格式无效")
        return raw

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        self._ensure_directory()
        fd, temporary_name = tempfile.mkstemp(
            prefix="authorized_devices.", suffix=".tmp", dir=self.path.parent
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            os.chmod(self.path, 0o600)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    def _locked_file(self):
        self._ensure_directory()
        handle = self.lock_path.open("a+", encoding="utf-8")
        os.chmod(self.lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def issue_device(self, name: str) -> tuple[str, str]:
        device_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        lock = self._locked_file()
        try:
            data = self._read_unlocked()
            now = _utc_now()
            data["devices"][device_id] = {
                "name": name,
                "token_hash": _token_hash(token),
                "created_at": now,
                "last_seen": now,
            }
            self._write_unlocked(data)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
        return device_id, token

    def authenticate(self, device_id: str, token: str) -> bool:
        record = self._read_unlocked()["devices"].get(device_id)
        if not isinstance(record, dict) or not isinstance(record.get("token_hash"), str):
            return False
        return hmac.compare_digest(record["token_hash"], _token_hash(token))

    def contains(self, device_id: str) -> bool:
        return device_id in self._read_unlocked()["devices"]

    def list_devices(self) -> list[dict[str, str]]:
        devices = []
        for device_id, record in self._read_unlocked()["devices"].items():
            devices.append(
                {
                    "device_id": device_id,
                    "name": str(record.get("name", "未知设备")),
                    "created_at": str(record.get("created_at", "")),
                    "last_seen": str(record.get("last_seen", "")),
                }
            )
        return sorted(devices, key=lambda item: item["created_at"])

    def revoke(self, device_id: str) -> bool:
        lock = self._locked_file()
        try:
            data = self._read_unlocked()
            existed = data["devices"].pop(device_id, None) is not None
            if existed:
                self._write_unlocked(data)
            return existed
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def clear(self) -> int:
        lock = self._locked_file()
        try:
            data = self._read_unlocked()
            count = len(data["devices"])
            if count:
                self._write_unlocked(self._empty_data())
            return count
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()


class PairingError(Exception):
    pass


class PairingBusy(PairingError):
    pass


class PairingRateLimited(PairingError):
    pass


class PairingInvalid(PairingError):
    pass


@dataclass
class PairingChallenge:
    challenge_id: str
    device_name: str
    client_ip: str
    code: str
    expires_at: float
    attempts: int = 0
    process: asyncio.subprocess.Process | None = None
    watcher: asyncio.Task[None] | None = None


class PairingManager:
    def __init__(
        self,
        store: DeviceStore,
        *,
        lifetime_seconds: int = 120,
        max_attempts: int = 5,
        max_starts_per_minute: int = 3,
    ) -> None:
        self.store = store
        self.lifetime_seconds = lifetime_seconds
        self.max_attempts = max_attempts
        self.max_starts_per_minute = max_starts_per_minute
        self._active: PairingChallenge | None = None
        self._start_history: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def start(self, device_name: str, client_ip: str) -> PairingChallenge:
        async with self._lock:
            now = time.monotonic()
            await self._expire_if_needed(now)
            if self._active:
                if (
                    self._active.client_ip == client_ip
                    and self._active.device_name == device_name
                ):
                    return self._active
                raise PairingBusy("另一台设备正在配对")

            history = self._start_history[client_ip]
            while history and now - history[0] >= 60:
                history.popleft()
            if len(history) >= self.max_starts_per_minute:
                raise PairingRateLimited("配对请求过于频繁，请稍后再试")
            history.append(now)

            challenge = PairingChallenge(
                challenge_id=secrets.token_urlsafe(18),
                device_name=device_name,
                client_ip=client_ip,
                code=f"{secrets.randbelow(1_000_000):06d}",
                expires_at=now + self.lifetime_seconds,
            )
            try:
                challenge.process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(PAIRING_DIALOG_PATH),
                    device_name,
                    challenge.code,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except Exception as exc:
                raise PairingError("无法在 Mac 上显示配对码") from exc

            self._active = challenge
            challenge.watcher = asyncio.create_task(
                self._watch_dialog(challenge), name="airmac-pairing-dialog"
            )
            return challenge

    async def complete(
        self, challenge_id: str, code: str, client_ip: str
    ) -> tuple[str, str, str]:
        async with self._lock:
            now = time.monotonic()
            await self._expire_if_needed(now)
            challenge = self._active
            if (
                challenge is None
                or challenge.challenge_id != challenge_id
                or challenge.client_ip != client_ip
            ):
                raise PairingInvalid("配对请求无效或已过期")

            challenge.attempts += 1
            if not hmac.compare_digest(challenge.code, code):
                if challenge.attempts >= self.max_attempts:
                    await self._invalidate(challenge)
                raise PairingInvalid("验证码错误")

            try:
                device_id, token = await asyncio.to_thread(
                    self.store.issue_device, challenge.device_name
                )
            except Exception as exc:
                raise PairingError("无法保存设备凭据") from exc
            device_name = challenge.device_name
            await self._invalidate(challenge)
            return device_id, token, device_name

    async def close(self) -> None:
        async with self._lock:
            if self._active:
                await self._invalidate(self._active)

    async def _watch_dialog(self, challenge: PairingChallenge) -> None:
        assert challenge.process is not None
        try:
            await challenge.process.wait()
        except asyncio.CancelledError:
            return
        async with self._lock:
            if self._active is challenge:
                self._active = None

    async def _expire_if_needed(self, now: float) -> None:
        if self._active and now >= self._active.expires_at:
            await self._invalidate(self._active)

    async def _invalidate(self, challenge: PairingChallenge) -> None:
        if self._active is challenge:
            self._active = None
        if challenge.process and challenge.process.returncode is None:
            try:
                challenge.process.terminate()
            except ProcessLookupError:
                pass
        if challenge.watcher and challenge.watcher is not asyncio.current_task():
            challenge.watcher.cancel()
            await asyncio.gather(challenge.watcher, return_exceptions=True)
