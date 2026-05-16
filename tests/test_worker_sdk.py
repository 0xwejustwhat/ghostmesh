from __future__ import annotations

import httpx

from ghostmesh.artifacts import LocalGitArtifactStore
from ghostmesh.sdk import WorkerClient
from tests.helpers import artifact_ref


def test_worker_client_claims_and_submits_through_pipes(monkeypatch) -> None:
    requests: list[tuple[str, dict[str, object], dict[str, str]]] = []
    get_requests: list[tuple[str, dict[str, str]]] = []

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
            json=json["artifact_refs"],
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        get_requests.append((url, headers))
        return httpx.Response(
            200,
            json={"lease": {"id": "lease-1"}, "card": {"id": "card-1"}, "history": []},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = WorkerClient("http://mesh.local", worker_id="worker-1", auth_token="lease-token")

    lease = client.claim(input_pipe="worker_input", idempotency_key="claim-key")
    artifact_refs = client.submit(
        lease_id=lease["id"],
        output_pipe="worker_output",
        artifact_refs=[artifact_ref(card_id="11111111-1111-1111-1111-111111111111")],
        idempotency_key="submit-key",
    )
    renewed = client.renew(
        lease_id=lease["id"],
        lease_seconds=600,
        idempotency_key="renew-key",
    )
    released = client.release(lease_id=lease["id"], idempotency_key="release-key")
    context = client.context(lease_id=lease["id"])

    assert lease["id"] == "lease-1"
    assert artifact_refs[0]["metadata"]["role"] == "draft"
    assert renewed["renewed"] is True
    assert released["released"] is True
    assert context["card"]["id"] == "card-1"
    assert requests[0] == (
        "http://mesh.local/cards/claim",
        {"input_pipe": "worker_input", "worker_id": "worker-1", "lease_seconds": 300},
        {"Idempotency-Key": "claim-key", "Authorization": "Bearer lease-token"},
    )
    assert requests[1] == (
        "http://mesh.local/cards/submit",
        {
            "lease_id": "lease-1",
            "output_pipe": "worker_output",
            "artifact_refs": [
                {
                    "card_id": "11111111-1111-1111-1111-111111111111",
                    "content_hash": "sha256:" + ("a" * 64),
                    "content_type": "text/plain",
                    "created_at": artifact_refs[0]["created_at"],
                    "event_id": None,
                    "id": artifact_refs[0]["id"],
                    "metadata": {"role": "draft"},
                    "size_bytes": 12,
                    "storage_ref": (
                        "git:working-tree:artifacts/"
                        "11111111-1111-1111-1111-111111111111/draft.txt"
                    ),
                }
            ],
        },
        {"Idempotency-Key": "submit-key", "Authorization": "Bearer lease-token"},
    )
    assert requests[2] == (
        "http://mesh.local/leases/lease-1/renew",
        {"lease_seconds": 600},
        {"Idempotency-Key": "renew-key", "Authorization": "Bearer lease-token"},
    )
    assert requests[3] == (
        "http://mesh.local/leases/lease-1/release",
        {"actor_id": "worker-1"},
        {"Idempotency-Key": "release-key", "Authorization": "Bearer lease-token"},
    )
    assert get_requests[0] == (
        "http://mesh.local/workers/leases/lease-1/context",
        {"Authorization": "Bearer lease-token"},
    )


def test_worker_client_uploads_bytes_through_artifact_store(tmp_path) -> None:
    client = WorkerClient("http://mesh.local", worker_id="worker-1")
    store = LocalGitArtifactStore(tmp_path)
    artifact = client.upload_bytes(
        store,
        card_id="11111111-1111-1111-1111-111111111111",
        data=b"hello",
        filename="draft.txt",
        content_type="text/plain",
        metadata={"role": "draft"},
    )

    assert artifact.content_hash == (
        "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e730"
        "43362938b9824"
    )
    assert artifact.storage_ref.startswith("file://")
    assert artifact.metadata == {"role": "draft"}


def test_worker_client_can_send_participant_header_without_changing_worker_id(monkeypatch) -> None:
    requests: list[tuple[dict[str, object], dict[str, str]]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        requests.append((json, headers))
        return httpx.Response(
            200,
            json={"id": "lease-1", "input_pipe": json["input_pipe"]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = WorkerClient(
        "http://mesh.local",
        worker_id="lease-worker",
        participant_id="participant-worker",
    )

    client.claim(input_pipe="worker_input")

    assert requests[0] == (
        {"input_pipe": "worker_input", "worker_id": "lease-worker", "lease_seconds": 300},
        {"X-Ghostmesh-Participant": "participant-worker"},
    )
