"""What the model calls cost, counted from each answer's `usage` (docs/BASETEN-PRICING.md, last section).

Prices come from agent/baseten_pricing.json by provider and model. A model with no price there is refused rather
than counted as free, and an answer with no `usage` is an error."""

import json
import threading
from pathlib import Path

PRICES = Path(__file__).resolve().parent / "baseten_pricing.json"


class CapReached(RuntimeError):
    """The spend cap is reached; no more requests are sent."""


def price(provider, model, path=PRICES):
    """Dollars per million tokens for input, cached input and output: {"input", "input_cached", "output"}."""
    p = json.loads(Path(path).read_text())
    if provider == "baseten":
        found = p.get("usd_per_million_tokens") if model == p.get("model") else None
    elif provider == "meta":
        found = p.get("meta", {}).get("models", {}).get(model, {}).get("usd_per_million_tokens")
    elif provider in ("fireworks", "modal"):
        sec = p.get(provider, {})
        found = sec.get("usd_per_million_tokens") if model == sec.get("model") else None
    else:
        found = None
    if not found:
        raise KeyError(f"no price for {model!r} on {provider!r} in {Path(path).name}")
    return {k: float(found[k]) for k in ("input", "input_cached", "output")}


def cost(prices, usage):
    """Dollars for one answer: uncached input, cached input and output, each at its own price."""
    if not usage:
        raise ValueError("the answer carried no usage, so its cost cannot be counted")
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    out = int(usage.get("completion_tokens") or 0)
    cached = min(cached, prompt)
    return ((prompt - cached) * prices["input"] + cached * prices["input_cached"] + out * prices["output"]) / 1e6


class Meter:
    """Calls and dollars so far, kept in `path` when given, and a cap that stops requests once reached."""

    def __init__(self, prices, cap_usd=5.0, path=None):
        self.prices = dict(prices)
        self.cap_usd = float(cap_usd)
        self.path = Path(path) if path else None
        self.calls = 0
        self.usd = 0.0
        self._lock = threading.Lock()
        if self.path and self.path.is_file():
            saved = json.loads(self.path.read_text())
            self.calls, self.usd = int(saved.get("calls", 0)), float(saved.get("usd", 0.0))

    def check(self):
        if self.usd >= self.cap_usd:
            raise CapReached(f"spend cap reached: ${self.usd:.4f} of ${self.cap_usd:g}; raise --spend-cap to go on")

    def add(self, usage):
        c = cost(self.prices, usage)
        with self._lock:
            self.calls += 1
            self.usd += c
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps({"calls": self.calls, "usd": self.usd}))
        return c

    def summary(self):
        return {"calls": self.calls, "usd": round(self.usd, 6), "cap_usd": self.cap_usd}
