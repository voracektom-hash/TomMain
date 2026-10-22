"""Push notifications via ntfy (https://ntfy.sh) – free, with photo, link and call button."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from hlidac.notify.base import Message, NotifyError

TIMEOUT_S = 15


class NtfyNotifier:
    channel = "ntfy"

    def __init__(self, server: str = "https://ntfy.sh", token: str | None = None):
        self.server = server.rstrip("/")
        self.token = token

    def payload(self, topic: str, m: Message) -> dict:
        data: dict = {"topic": topic, "title": m.title, "message": m.body,
                      "priority": m.priority}
        if m.tags:
            data["tags"] = m.tags
        if m.url:
            data["click"] = m.url
        if m.image_url:
            data["attach"] = m.image_url
            data["filename"] = "foto.jpg"
        actions = []
        if m.url:
            actions.append({"action": "view", "label": "Inzerát", "url": m.url})
        if m.phone:
            actions.append({"action": "view", "label": "Zavolat", "url": f"tel:{m.phone}"})
        if actions:
            data["actions"] = actions
        return data

    def send(self, recipient: str, message: Message) -> None:
        body = json.dumps(self.payload(recipient, message)).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.server, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise NotifyError(f"ntfy HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NotifyError(f"ntfy nedostupné: {exc}") from exc
