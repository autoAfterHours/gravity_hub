"""orbit360/ui/_ui_utils.py — shared helpers for UI panels."""
from __future__ import annotations


def fmt_dur(secs: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    if secs < 60:
        return f"{secs:.0f}s"
    m, s = divmod(int(secs), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"
