"""
event_bus.py — Orbit360 central event bus.

A singleton QObject that re-publishes all RunWorker/sync/screenshot signals
so any component can subscribe without holding a direct reference to the
worker instance.

Usage:
    from orbit360.backend.event_bus import bus

    # Producer (RunWorker connects its signals here at run start):
    worker.run_started.connect(bus.run_started)

    # Consumer (GUI or headless logger subscribes once at startup):
    bus.run_started.connect(my_handler)

The bus uses Qt.ConnectionType.UniqueConnection on consumer subscriptions so
repeated run starts don't accumulate duplicate handler connections.

Worker signals are forwarded to the bus (not replaced) so direct
worker→handler connections still work if needed for legacy compatibility.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class _EventBus(QObject):
    # ── Run lifecycle ──────────────────────────────────────────────────── #
    run_started            = Signal(str)            # run_root path
    script_started         = Signal(str, int, int)  # name, index, total
    script_finished        = Signal(object)         # ScriptResult
    progress_updated       = Signal(str, str)       # script_name, line
    run_completed          = Signal(str, int, int, int)  # summary_path, p, f, e
    run_aborted            = Signal(str, int, int, int)  # summary_path, p, f, e
    run_failed             = Signal(str)            # error message

    # ── Input prompts ──────────────────────────────────────────────────── #
    manual_input_required  = Signal(str)            # prompt text
    failure_input_required = Signal(str)            # failure recovery prompt
    value_input_requested  = Signal(str)            # field label

    # ── Worker lifetime ────────────────────────────────────────────────── #
    worker_finished        = Signal()               # mirrors QThread.finished

    # ── Git sync ───────────────────────────────────────────────────────── #
    sync_finished          = Signal(bool, str)      # success, message

    # ── Screenshots ────────────────────────────────────────────────────── #
    new_screenshot         = Signal(str)            # absolute path to PNG

    # ── Structured log (enhanced logging, Phase 2+) ───────────────────── #
    # Emitted by OrbitLogger in addition to file writing so any subscriber
    # (GUI log console, headless stdout, future webhook) can consume events.
    log_entry              = Signal(str, str, str)  # message, level, source


# Module-level singleton — no parent so it outlives any window instance.
bus = _EventBus()
