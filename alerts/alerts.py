"""Alert manager for threshold-based notifications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class AlertThreshold:
    """Threshold configuration for an alert."""

    name: str
    metric: str
    threshold: float
    critical: bool = False
    window_seconds: int = 300


class AlertManager:
    """Manages alert thresholds and notifications."""

    def __init__(self):
        self._thresholds: list[AlertThreshold] = []
        self._handlers: list[Callable[[AlertThreshold, dict], None]] = []

    def add_threshold(self, threshold: AlertThreshold) -> None:
        """Add a threshold to monitor."""
        self._thresholds.append(threshold)

    def add_handler(self, handler: Callable[[AlertThreshold, dict], None]) -> None:
        """Add a notification handler."""
        self._handlers.append(handler)

    def check_metrics(self, metrics: dict) -> list[tuple[AlertThreshold, dict]]:
        """Check current metrics against thresholds."""
        alerts = []
        for t in self._thresholds:
            current = metrics.get(t.metric)
            if current is not None and current > t.threshold:
                alerts.append((t, {"metric": t.metric, "value": current, "threshold": t.threshold}))
        return alerts

    async def notify(self, alerts: list[tuple[AlertThreshold, dict]]) -> None:
        """Send notifications for alerts."""
        for threshold, data in alerts:
            for handler in self._handlers:
                await handler(threshold, data)
