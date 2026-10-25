"""Small JSON state so restarts do not retry the same message forever."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_ENTRIES = 2000


class State:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {"processed": [], "attempts": {}}
        self._load()

    def _load(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                self.data["processed"] = list(parsed.get("processed", []))[-MAX_ENTRIES:]
                self.data["attempts"] = dict(parsed.get("attempts", {}))
        except FileNotFoundError:
            log.debug("no state file at %s yet", self.path)
        except (OSError, ValueError) as exc:
            log.warning("state file unreadable, starting fresh: %s", exc)

    def _save(self) -> None:
        self.data["processed"] = self.data["processed"][-MAX_ENTRIES:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("cannot write state file: %s", exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def is_processed(self, message_id: str) -> bool:
        return message_id in self.data["processed"]

    def mark_processed(self, message_id: str) -> None:
        self.data["processed"].append(message_id)
        self.data["attempts"].pop(message_id, None)
        self._save()

    def bump_attempt(self, message_id: str) -> int:
        attempts = int(self.data["attempts"].get(message_id, 0)) + 1
        self.data["attempts"][message_id] = attempts
        self._save()
        return attempts
