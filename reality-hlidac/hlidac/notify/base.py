"""Notification channels share one tiny interface, so SMS providers can be swapped in."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class NotifyError(Exception):
    """Sending failed; the alert stays queued and is retried."""


@dataclass
class Message:
    title: str          # rich channels (ntfy)
    body: str           # rich channels, may contain diacritics and newlines
    sms: str            # plain ASCII, ≤ 2 SMS segments
    url: str | None = None
    image_url: str | None = None
    phone: str | None = None   # broker phone for a "call" button
    priority: int = 3          # ntfy: 1 (min) … 5 (urgent)
    tags: list[str] = field(default_factory=list)


class Notifier(Protocol):
    channel: str

    def send(self, recipient: str, message: Message) -> None:
        """Deliver the message or raise NotifyError."""
