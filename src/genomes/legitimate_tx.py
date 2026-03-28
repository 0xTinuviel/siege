"""Legitimate transaction templates — Section 2.3 of the spec."""

from __future__ import annotations

import json
from pathlib import Path

from src.models import LegitimateTransaction


def load_legitimate_transactions(path: str | Path | None = None) -> list[LegitimateTransaction]:
    if path is None:
        path = Path(__file__).parent.parent.parent / "data" / "legitimate_transactions.json"
    path = Path(path)
    with open(path) as f:
        data = json.load(f)
    txs = data.get("legitimate_transactions", data if isinstance(data, list) else [])
    return [LegitimateTransaction.from_dict(tx) for tx in txs]
