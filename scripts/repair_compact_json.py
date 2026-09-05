#!/usr/bin/env python3
"""Normalize the compact audit's independent replay value for JSON evidence."""
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "code/ai_pilot/benchmarks/compact_event_slot_audit.py"
text = path.read_text()
old = '        "replayed_event_count": replay_value,\n'
new = '        "replayed_event_count": None if replay_value is None else int(replay_value),\n'
if new not in text:
    if old not in text:
        raise RuntimeError("missing replayed_event_count serialization anchor")
    text = text.replace(old, new, 1)
path.write_text(text)
print("compact JSON scalar normalization: PASS")
