"""Helpers for race tests on real overlapping SQLite connections (Gate D-2).

- `start` runs a task in a named thread and records its value or exception.
- `finish` / `finish_error` join the thread, require that it ended, and require
  exactly the expected outcome: a value (no exception) or the expected exception.
  A missing value is never read as None, so an unexpected exception or a hung
  worker always fails the test.
- `LockProbe` wraps the account write lock (`storage.begin_card_write`, also the
  name bound in `migration`) and records, per thread name, when a task starts
  waiting for the lock and when it holds it. Tests assert the order
  (holder acquired -> other waiting -> holder released -> other acquired) instead
  of relying on sleep/is_alive.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable
from unittest import mock

from app.srs import migration, storage

JOIN_TIMEOUT = 20


@dataclass
class Task:
    name: str
    thread: threading.Thread
    box: dict = field(default_factory=dict)


def start(name: str, target: Callable[[], Any]) -> Task:
    task = Task(name, None)  # type: ignore[arg-type]

    def wrapper() -> None:
        try:
            task.box["value"] = target()
        except BaseException as error:  # noqa: BLE001 - handed to the test
            task.box["error"] = error

    task.thread = threading.Thread(target=wrapper, name=name, daemon=True)
    task.thread.start()
    return task


def finish(test, task: Task) -> Any:
    task.thread.join(JOIN_TIMEOUT)
    test.assertFalse(task.thread.is_alive(), f"{task.name} did not finish")
    if "error" in task.box:
        test.fail(f"{task.name} raised {task.box['error']!r}")
    test.assertIn("value", task.box, f"{task.name} produced no result")
    return task.box["value"]


def finish_error(test, task: Task, error_type: type, code: str | None = None) -> BaseException:
    task.thread.join(JOIN_TIMEOUT)
    test.assertFalse(task.thread.is_alive(), f"{task.name} did not finish")
    test.assertNotIn("value", task.box, f"{task.name} returned instead of failing")
    test.assertIn("error", task.box, f"{task.name} produced no result")
    error = task.box["error"]
    test.assertIsInstance(error, error_type, f"{task.name} raised {error!r}")
    if code is not None:
        test.assertEqual(getattr(error, "code", None), code)
    return error


class LockProbe:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self._cond = threading.Condition()
        real = storage.begin_card_write

        def wrapped(connection: Any, user_id: int) -> None:
            self.mark("waiting")
            real(connection, user_id)
            self.mark("acquired")

        self._patches = [mock.patch.object(storage, "begin_card_write", wrapped),
                         mock.patch.object(migration, "begin_card_write", wrapped)]

    def __enter__(self) -> "LockProbe":
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        for patch in self._patches:
            patch.stop()

    def mark(self, what: str, who: str | None = None) -> None:
        with self._cond:
            self.events.append((what, who or threading.current_thread().name))
            self._cond.notify_all()

    def wait(self, what: str, who: str, timeout: float = 10) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: (what, who) in self.events, timeout)

    def index(self, what: str, who: str) -> int:
        return self.events.index((what, who))

    def assert_serialized(self, test, holder: str, waiter: str) -> None:
        """holder acquired < waiter waiting < holder released < waiter acquired."""
        for entry in (("acquired", holder), ("waiting", waiter), ("released", holder), ("acquired", waiter)):
            test.assertIn(entry, self.events, f"missing {entry} in {self.events}")
        test.assertLess(self.index("acquired", holder), self.index("waiting", waiter))
        test.assertLess(self.index("waiting", waiter), self.index("released", holder))
        test.assertLess(self.index("released", holder), self.index("acquired", waiter),
                        f"{waiter} got the lock before {holder} released it: {self.events}")
