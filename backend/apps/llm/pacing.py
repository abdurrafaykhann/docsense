"""Free-tier pacing: enforce a minimum interval between requests to one provider."""

from __future__ import annotations

import time


class Paced:
    """Proxy for a chat model: sleeps so consecutive structured-output calls are spaced out."""

    def __init__(self, model, min_interval: float, sleep=time.sleep, clock=time.monotonic):
        self.model, self.min_interval = model, min_interval
        self._last: float | None = None
        self._sleep, self._clock = sleep, clock

    def with_structured_output(self, schema):
        runnable = self.model.with_structured_output(schema)
        outer = self

        class _R:
            def invoke(self, messages):
                wait = outer.min_interval - (outer._clock() - (outer._last or 0.0))
                if outer._last is not None and wait > 0:
                    outer._sleep(wait)
                try:
                    return runnable.invoke(messages)
                finally:
                    outer._last = outer._clock()

        return _R()
