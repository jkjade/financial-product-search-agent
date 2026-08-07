from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass
class ColumnProfile:
    canonical_type: str
    missing: int = 0
    non_null: int = 0
    invalid: int = 0
    min_value: str | None = None
    max_value: str | None = None
    max_length: int = 0
    samples: list[str] = field(default_factory=list)
    _distinct: set[str] = field(default_factory=set, repr=False)
    distinct_capped: bool = False

    def observe(self, raw: str | None, cleaned: str | None, distinct_cap: int = 1000) -> None:
        raw_present = raw is not None and str(raw).strip() != ""
        if cleaned is None:
            self.missing += 1
            if raw_present:
                self.invalid += 1
            return
        self.non_null += 1
        text = str(cleaned)
        self.max_length = max(self.max_length, len(text))
        if len(self.samples) < 5 and text not in self.samples:
            self.samples.append(text)
        if not self.distinct_capped:
            self._distinct.add(text)
            if len(self._distinct) > distinct_cap:
                self.distinct_capped = True
                self._distinct.clear()
        if self.canonical_type in {"numeric", "integer"}:
            try:
                value = Decimal(text)
            except InvalidOperation:
                return
            if self.min_value is None or value < Decimal(self.min_value):
                self.min_value = text
            if self.max_value is None or value > Decimal(self.max_value):
                self.max_value = text
        elif self.canonical_type == "date":
            if self.min_value is None or text < self.min_value:
                self.min_value = text
            if self.max_value is None or text > self.max_value:
                self.max_value = text

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_type": self.canonical_type,
            "missing": self.missing,
            "non_null": self.non_null,
            "invalid": self.invalid,
            "distinct_count": None if self.distinct_capped else len(self._distinct),
            "distinct_count_capped": self.distinct_capped,
            "min": self.min_value,
            "max": self.max_value,
            "max_length": self.max_length,
            "samples": self.samples,
        }
