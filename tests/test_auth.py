from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path

import pytest

import auth
from auth import (
    DeviceStore,
    DeviceStoreError,
    PAIRING_DIALOG_PATH,
    PairingBusy,
    PairingChallenge,
    PairingInvalid,
    PairingManager,
    PairingRateLimited,
)


class FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.finished = asyncio.Event()

    async def wait(self) -> int:
        await self.finished.wait()
        assert self.returncode is not None
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15
        self.finished.set()


def test_device_store_hashes_tokens_and_revokes(tmp_path: Path) -> None:
    store_path = tmp_path / "AirMac" / "authorized_devices.json"
    store = DeviceStore(store_path)

    device_id, token = store.issue_device("Test iPhone")

    persisted = json.loads(store_path.read_text(encoding="utf-8"))
    record = persisted["devices"][device_id]
    assert token not in store_path.read_text(encoding="utf-8")
    assert len(record["token_hash"]) == 64
    assert store.authenticate(device_id, token)
    assert DeviceStore(store_path).authenticate(device_id, token)
    assert not store.authenticate(device_id, token + "invalid")
    assert stat.S_IMODE(store_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store_path.parent.stat().st_mode) == 0o700

    assert store.list_devices()[0]["name"] == "Test iPhone"
    previous_last_seen = store.list_devices()[0]["last_seen"]
    assert store.touch(device_id, min_interval_seconds=0)
    assert store.list_devices()[0]["last_seen"] > previous_last_seen
    assert store.revoke(device_id)
    assert not store.contains(device_id)
    assert not store.revoke(device_id)


def test_device_store_uses_atomic_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store_path = tmp_path / "AirMac" / "authorized_devices.json"
    replacements: list[tuple[Path, Path]] = []
    real_replace = auth.os.replace

    def recording_replace(source: str | Path, destination: str | Path) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(auth.os, "replace", recording_replace)
    DeviceStore(store_path).issue_device("Atomic Phone")

    assert len(replacements) == 1
    temporary_path, destination = replacements[0]
    assert destination == store_path
    assert temporary_path.parent == store_path.parent
    assert not temporary_path.exists()


def test_device_store_clear(tmp_path: Path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    store.issue_device("One")
    store.issue_device("Two")
    assert store.clear() == 2
    assert store.clear() == 0
    assert store.list_devices() == []


def test_device_store_fails_closed_on_corruption(tmp_path: Path) -> None:
    store_path = tmp_path / "devices.json"
    store_path.write_text("not-json", encoding="utf-8")
    store = DeviceStore(store_path)
    with pytest.raises(DeviceStoreError):
        store.list_devices()


@pytest.mark.asyncio
async def test_pairing_dialog_uses_fixed_program_and_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []
    process = FakeProcess()

    async def fake_create_subprocess_exec(*args: object, **_: object) -> FakeProcess:
        calls.append(args)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    store = DeviceStore(tmp_path / "devices.json")
    manager = PairingManager(store)
    malicious_name = 'iPhone" & do shell script "touch /tmp/owned" & "'

    challenge = await manager.start(malicious_name, "192.168.1.20")

    assert calls[0][1] == str(PAIRING_DIALOG_PATH)
    assert calls[0][2] == malicious_name
    assert calls[0][3] == challenge.code
    device_id, token, name = await manager.complete(
        challenge.challenge_id, challenge.code, "192.168.1.20"
    )
    assert name == malicious_name
    assert store.authenticate(device_id, token)
    with pytest.raises(PairingInvalid):
        await manager.complete(
            challenge.challenge_id, challenge.code, "192.168.1.20"
        )
    await manager.close()


@pytest.mark.asyncio
async def test_pairing_rejects_wrong_expired_and_replayed_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    processes: list[FakeProcess] = []

    async def fake_create_subprocess_exec(*_: object, **__: object) -> FakeProcess:
        process = FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    manager = PairingManager(DeviceStore(tmp_path / "devices.json"), max_attempts=2)
    challenge = await manager.start("Phone", "192.168.1.21")

    with pytest.raises(PairingInvalid):
        await manager.complete(challenge.challenge_id, "111111", "192.168.1.21")
    with pytest.raises(PairingInvalid):
        await manager.complete(challenge.challenge_id, "222222", "192.168.1.21")
    with pytest.raises(PairingInvalid):
        await manager.complete(challenge.challenge_id, challenge.code, "192.168.1.21")

    expiring = PairingManager(
        DeviceStore(tmp_path / "expired.json"), lifetime_seconds=0
    )
    expired = await expiring.start("Phone", "192.168.1.22")
    with pytest.raises(PairingInvalid):
        await expiring.complete(expired.challenge_id, expired.code, "192.168.1.22")
    await manager.close()
    await expiring.close()


@pytest.mark.asyncio
async def test_pairing_start_is_idempotent_busy_and_concurrency_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def fake_create_subprocess_exec(*_: object, **__: object) -> FakeProcess:
        nonlocal calls
        calls += 1
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    manager = PairingManager(DeviceStore(tmp_path / "devices.json"))

    first = await manager.start("Phone", "192.168.1.30")
    repeated = await manager.start("Phone", "192.168.1.30")
    assert repeated is first
    assert calls == 1
    with pytest.raises(PairingBusy):
        await manager.start("Other", "192.168.1.31")
    await manager.close()

    results = await asyncio.gather(
        manager.start("One", "192.168.1.32"),
        manager.start("Two", "192.168.1.33"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, PairingChallenge) for result in results) == 1
    assert sum(isinstance(result, PairingBusy) for result in results) == 1
    await manager.close()


@pytest.mark.asyncio
async def test_pairing_start_rate_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create_subprocess_exec(*_: object, **__: object) -> FakeProcess:
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    manager = PairingManager(
        DeviceStore(tmp_path / "devices.json"), max_starts_per_minute=1
    )
    await manager.start("Phone", "192.168.1.40")
    await manager.close()
    with pytest.raises(PairingRateLimited):
        await manager.start("Phone", "192.168.1.40")
