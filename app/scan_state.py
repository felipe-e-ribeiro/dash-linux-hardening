import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_state: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def set_running(target_id: str) -> None:
    with _lock:
        _state[target_id] = {"status": "running", "started_at": _now()}


def set_success(target_id: str, report_id: str) -> None:
    with _lock:
        _state[target_id] = {
            "status": "success",
            "last_scan": _now(),
            "report_id": report_id,
            "last_error": None,
        }


def set_failed(target_id: str, error: str) -> None:
    with _lock:
        _state[target_id] = {
            "status": "failed",
            "last_scan": _now(),
            "last_error": error,
            "report_id": None,
        }


def get_state(target_id: str) -> dict:
    with _lock:
        return dict(_state.get(target_id, {"status": "idle"}))


def is_running(target_id: str) -> bool:
    with _lock:
        return _state.get(target_id, {}).get("status") == "running"
