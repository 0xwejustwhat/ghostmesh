from __future__ import annotations

from typing import Any

import httpx


class WorkerClient:
    """Minimal pipe-aware client for workers.

    Workers claim via an input pipe and submit via an output pipe. The client does
    not expose global graph concepts.
    """

    def __init__(self, base_url: str, *, worker_id: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        self.timeout = timeout

    def claim(
        self,
        *,
        input_pipe: str,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/cards/claim",
            json={
                "input_pipe": input_pipe,
                "worker_id": self.worker_id,
                "lease_seconds": lease_seconds,
            },
            headers=_idempotency_headers(idempotency_key),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def submit(
        self,
        *,
        lease_id: str,
        output_pipe: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/cards/submit",
            json={"lease_id": lease_id, "output_pipe": output_pipe, "payload": payload},
            headers=_idempotency_headers(idempotency_key),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def renew(
        self,
        *,
        lease_id: str,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/leases/{lease_id}/renew",
            json={"lease_seconds": lease_seconds},
            headers=_idempotency_headers(idempotency_key),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def release(
        self,
        *,
        lease_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/leases/{lease_id}/release",
            json={"actor_id": self.worker_id},
            headers=_idempotency_headers(idempotency_key),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


def _idempotency_headers(idempotency_key: str | None) -> dict[str, str]:
    return {"Idempotency-Key": idempotency_key} if idempotency_key else {}
