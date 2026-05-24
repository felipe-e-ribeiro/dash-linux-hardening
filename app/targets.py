import base64
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

_lock = threading.Lock()
_targets: list[dict] = []
_targets_path: Optional[Path] = None
_fernet: Optional[Fernet] = None


# ---------------------------------------------------------------------------
# Fernet key derived from Flask secret key
# ---------------------------------------------------------------------------

def get_fernet_key(secret_key: str) -> Fernet:
    # Derive a 32-byte key via SHA-256 of the secret, then base64url-encode
    raw = hashlib.sha256(secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_password(password: str, fernet: Fernet) -> str:
    return fernet.encrypt(password.encode()).decode()


def decrypt_password(enc: str, fernet: Fernet) -> str:
    return fernet.decrypt(enc.encode()).decode()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_targets(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with path.open() as f:
            return json.load(f)
    except Exception:
        return []


def save_targets(targets: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(targets, f, indent=2)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _save():
    if _targets_path:
        save_targets(_targets, _targets_path)


def all_targets() -> list:
    with _lock:
        return list(_targets)


def get_target(target_id: str) -> Optional[dict]:
    with _lock:
        return next((t for t in _targets if t["id"] == target_id), None)


def add_target(data: dict) -> dict:
    t = {
        "id": str(uuid.uuid4()),
        "host": data["host"].strip(),
        "port": int(data.get("port") or 22),
        "username": data["username"].strip(),
        "auth_type": data.get("auth_type", "key"),
        "password_enc": None,
        "profile": data.get("profile", ""),
        "schedule": data.get("schedule") or None,
        "last_scan": None,
        "last_status": None,
        "last_error": None,
        "history": [],
        "os_id": None,
        "os_version": None,
    }
    if t["auth_type"] == "password" and data.get("password") and _fernet:
        t["password_enc"] = encrypt_password(data["password"], _fernet)
    with _lock:
        # Reject duplicate host+port
        for existing in _targets:
            if existing["host"] == t["host"] and existing["port"] == t["port"]:
                raise ValueError(f"Target {t['host']}:{t['port']} already exists.")
        _targets.append(t)
        _save()
    return t


def update_target(target_id: str, data: dict) -> dict:
    with _lock:
        t = next((t for t in _targets if t["id"] == target_id), None)
        if t is None:
            raise KeyError(target_id)
        t["host"] = data.get("host", t["host"]).strip()
        t["port"] = int(data.get("port") or t["port"])
        t["username"] = data.get("username", t["username"]).strip()
        t["auth_type"] = data.get("auth_type", t["auth_type"])
        t["profile"] = data.get("profile", t["profile"])
        t["schedule"] = data.get("schedule") or None
        if t["auth_type"] == "password" and data.get("password") and _fernet:
            t["password_enc"] = encrypt_password(data["password"], _fernet)
        _save()
        return t


def remove_target(target_id: str) -> None:
    with _lock:
        idx = next((i for i, t in enumerate(_targets) if t["id"] == target_id), None)
        if idx is not None:
            _targets.pop(idx)
            _save()


def update_scan_result(target_id: str, status: str, report_id: str = None,
                       error: str = None, os_id: str = None, os_version: str = None) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        t = next((t for t in _targets if t["id"] == target_id), None)
        if t is None:
            return
        t["last_scan"] = ts
        t["last_status"] = status
        t["last_error"] = error
        if os_id:
            t["os_id"] = os_id
        if os_version:
            t["os_version"] = os_version
        entry = {"ts": ts, "status": status, "report_id": report_id, "error": error}
        t["history"] = ([entry] + t.get("history", []))[:10]
        _save()


# ---------------------------------------------------------------------------
# Module initialisation (called from create_app)
# ---------------------------------------------------------------------------

def init(data_dir: Path, secret_key: str) -> None:
    global _targets, _targets_path, _fernet
    _fernet = get_fernet_key(secret_key)
    _targets_path = data_dir / "targets.json"
    loaded = load_targets(_targets_path)
    with _lock:
        _targets = loaded
