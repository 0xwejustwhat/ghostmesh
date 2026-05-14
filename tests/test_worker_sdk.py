from __future__ import annotations

import httpx

from ghostmesh.sdk import WorkerClient


def test_worker_client_claims_and_submits_through_pipes(monkeypatch) -> None:
    requests: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        requests.append((url, json, headers))
        request = httpx.Request("POST", url)
        if url.endswith("/cards/claim"):
            return httpx.Response(
                200,
                json={"id": "lease-1", "input_pipe": json["input_pipe"]},
                request=request,
            )
        if url.endswith("/renew"):
            return httpx.Response(200, json={"id": "lease-1", "renewed": True}, request=request)
        if url.endswith("/release"):
            return httpx.Response(200, json={"id": "lease-1", "released": True}, request=request)
        return httpx.Response(
            200,
            json={"id": "artifact-1", "payload": json["payload"]},
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = WorkerClient("http://mesh.local", worker_id="worker-1")

    lease = client.claim(input_pipe="worker_input", idempotency_key="claim-key")
    artifact = client.submit(
        lease_id=lease["id"],
        output_pipe="worker_output",
        payload={"answer": "done"},
        idempotency_key="submit-key",
    )
    renewed = client.renew(
        lease_id=lease["id"],
        lease_seconds=600,
        idempotency_key="renew-key",
    )
    released = client.release(lease_id=lease["id"], idempotency_key="release-key")

    assert lease["id"] == "lease-1"
    assert artifact["payload"] == {"answer": "done"}
    assert renewed["renewed"] is True
    assert released["released"] is True
    assert requests[0] == (
        "http://mesh.local/cards/claim",
        {"input_pipe": "worker_input", "worker_id": "worker-1", "lease_seconds": 300},
        {"Idempotency-Key": "claim-key"},
    )
    assert requests[1] == (
        "http://mesh.local/cards/submit",
        {
            "lease_id": "lease-1",
            "output_pipe": "worker_output",
            "payload": {"answer": "done"},
        },
        {"Idempotency-Key": "submit-key"},
    )
    assert requests[2] == (
        "http://mesh.local/leases/lease-1/renew",
        {"lease_seconds": 600},
        {"Idempotency-Key": "renew-key"},
    )
    assert requests[3] == (
        "http://mesh.local/leases/lease-1/release",
        {"actor_id": "worker-1"},
        {"Idempotency-Key": "release-key"},
    )
