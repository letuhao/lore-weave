"""Compose healthcheck for the headless video-generation worker."""

from __future__ import annotations

import os
import sys
import time

from app.worker.heartbeat import (
    DEFAULT_MAX_AGE_S,
    heartbeat_is_fresh,
    heartbeat_path,
)


def _mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def main() -> int:
    max_age = float(os.environ.get("WORKER_HEARTBEAT_MAX_AGE_S", DEFAULT_MAX_AGE_S))
    return 0 if heartbeat_is_fresh(_mtime(heartbeat_path()), time.time(), max_age) else 1


if __name__ == "__main__":
    sys.exit(main())
