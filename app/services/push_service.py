from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)

_KEYS_FILE = Path("push_vapid_keys.json")
_SUBS_FILE = Path("push_subscriptions.json")


class PushService:
    """Web Push notification service using VAPID + pywebpush."""

    def __init__(
        self,
        keys_file: str | Path = _KEYS_FILE,
        subs_file: str | Path = _SUBS_FILE,
        contact_email: str = "admin@example.com",
    ) -> None:
        self._keys_path = Path(keys_file)
        self._subs_path = Path(subs_file)
        self._contact = contact_email
        self._vapid = self._load_or_create_keys()
        self._subs: dict[str, list[dict[str, Any]]] = self._load_subscriptions()

    # ------------------------------------------------------------------
    # VAPID keys
    # ------------------------------------------------------------------

    def _load_or_create_keys(self) -> Vapid:
        if self._keys_path.exists():
            data = json.loads(self._keys_path.read_text(encoding="utf-8"))
            v = Vapid()
            v.from_pem(data["private_key"].encode())
            return v
        v = Vapid()
        v.generate_keys()
        priv_pem = v.private_pem().decode()
        self._keys_path.write_text(
            json.dumps({"private_key": priv_pem}, indent=2),
            encoding="utf-8",
        )
        logger.info("Generated new VAPID keys → %s", self._keys_path)
        return v

    def public_key_b64(self) -> str:
        """Return VAPID public key as base64url (uncompressed EC point)."""
        pub_bytes = self._vapid.public_key.public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        return base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def _load_subscriptions(self) -> dict[str, list[dict[str, Any]]]:
        if self._subs_path.exists():
            try:
                return json.loads(self._subs_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _persist_subscriptions(self) -> None:
        self._subs_path.write_text(
            json.dumps(self._subs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def subscribe(self, employee_id: str, subscription: dict[str, Any]) -> None:
        """Save a push subscription for an employee, avoiding duplicates."""
        endpoint = subscription.get("endpoint", "")
        subs = self._subs.setdefault(employee_id, [])
        # Remove stale entry with the same endpoint
        self._subs[employee_id] = [s for s in subs if s.get("endpoint") != endpoint]
        self._subs[employee_id].append(subscription)
        self._persist_subscriptions()
        logger.info("Push subscription added for employee %s", employee_id)

    def unsubscribe(self, employee_id: str, endpoint: str) -> None:
        """Remove a push subscription by endpoint URL."""
        if employee_id in self._subs:
            self._subs[employee_id] = [
                s for s in self._subs[employee_id] if s.get("endpoint") != endpoint
            ]
            self._persist_subscriptions()
            logger.info("Push subscription removed for employee %s", employee_id)

    def has_subscription(self, employee_id: str) -> bool:
        return bool(self._subs.get(employee_id))

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send(
        self,
        employee_id: str,
        title: str,
        body: str,
        *,
        url: str = "/employee/payouts",
    ) -> None:
        """Send a push notification to all subscriptions of an employee."""
        subs = self._subs.get(employee_id)
        if not subs:
            return

        payload = json.dumps({"title": title, "body": body, "url": url})
        stale: list[str] = []

        for sub in list(subs):
            endpoint = sub.get("endpoint", "")
            try:
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=self._vapid,
                    vapid_claims={
                        "sub": f"mailto:{self._contact}",
                    },
                    ttl=3600,
                )
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                logger.warning(
                    "Push failed for employee %s endpoint %s: %s (status %s)",
                    employee_id, endpoint[:40], exc, status,
                )
                # 404 / 410 = subscription expired/removed
                if status in (404, 410):
                    stale.append(endpoint)
            except Exception as exc:
                logger.warning("Push error for employee %s: %s", employee_id, exc)

        for endpoint in stale:
            self.unsubscribe(employee_id, endpoint)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: PushService | None = None


def get_push_service() -> PushService:
    global _instance
    if _instance is None:
        _instance = PushService()
    return _instance
