"""Prints messages to the log instead of sending them – for local testing."""

from __future__ import annotations

import logging

from hlidac.notify.base import Message

log = logging.getLogger("hlidac")


class ConsoleNotifier:
    def __init__(self, channel: str = "console"):
        # channel='sms' lets the console stand in for a real SMS gateway.
        self.channel = channel

    def send(self, recipient: str, message: Message) -> None:
        if self.channel == "sms":
            log.info("[SMS → %s] %s", recipient, message.sms)
        else:
            log.info("[%s → %s] %s | %s", self.channel, recipient, message.title,
                     message.body.replace("\n", " | "))
