from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import TextIO


class TerminalActivity:
    """Display elapsed activity while a model request is in flight."""

    def __init__(self, stream: TextIO | None = None, interval: float = 0.15) -> None:
        self.stream = stream or sys.stdout
        self.interval = max(0.05, interval)

    @asynccontextmanager
    async def track(self, label: str) -> AsyncIterator[None]:
        started = time.monotonic()
        interactive = bool(getattr(self.stream, "isatty", lambda: False)())
        stopped = asyncio.Event()
        task: asyncio.Task[None] | None = None
        if interactive:
            task = asyncio.create_task(self._animate(label, started, stopped))
        else:
            print(f"  {label}...", file=self.stream, flush=True)
        try:
            yield
        finally:
            stopped.set()
            if task is not None:
                await task
                elapsed = time.monotonic() - started
                message = f"\r  {label}... done ({elapsed:.1f}s)"
                print(message.ljust(78), file=self.stream, flush=True)

    async def _animate(self, label: str, started: float, stopped: asyncio.Event) -> None:
        frames = "|/-\\"
        index = 0
        while not stopped.is_set():
            elapsed = time.monotonic() - started
            message = f"\r  {frames[index % len(frames)]} {label} ({elapsed:5.1f}s)"
            print(message.ljust(78), end="", file=self.stream, flush=True)
            index += 1
            with suppress(TimeoutError):
                await asyncio.wait_for(stopped.wait(), timeout=self.interval)
