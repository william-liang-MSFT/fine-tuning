"""Customer personas mapped to the 30-scenario evaluation harness.

Each persona's ``intent`` is keyed ``t<NN>_*`` to its corresponding scenario id in
``scenarios_train.json``. The actual data lives in ``personas.json`` (kept
JSON to avoid Python-quoting issues with non-ASCII characters in goal strings).

Drop-in usage::

    from personas import PERSONAS
"""
import json
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "personas.json"

with _DATA_PATH.open(encoding="utf-8") as _f:
    PERSONAS = json.load(_f)

_REQUIRED = {"name", "email", "order_id", "intent", "item", "reason", "goal"}
for _p in PERSONAS:
    missing = _REQUIRED - _p.keys()
    if missing:
        raise ValueError(f"Persona {_p.get('intent','?')} missing fields: {missing}")
    if _p.get("adversarial") and not _p.get("tactics"):
        raise ValueError(f"Persona {_p['intent']} marked adversarial but has no tactics")

__all__ = ["PERSONAS"]
