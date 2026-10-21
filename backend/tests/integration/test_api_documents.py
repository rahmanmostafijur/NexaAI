"""Knowledge-base administration through the API (upload -> index -> search -> delete)."""

import asyncio
import uuid

from app.core.config import get_settings


def markdown_file(text: str) -> dict:
    return {"file": (f"guide-{uuid.uuid4().hex[:6]}.md", text.encode(), "text/markdown")}


async def wait_for_status(client, headers, document_id: str, status: str) -> dict:
    """Indexing runs on the queue, so poll until the document reaches `status`."""
    deadline = asyncio.get_running_loop().time() + 30
    while True:
        detail = (await client.get(f"/api/documents/{document_id}", headers=headers)).json()
        if detail["status"] == status or asyncio.get_running_loop().time() > deadline:
            return detail
        await asyncio.sleep(0.05)


async def test_document_lifecycle(client, admin_headers) -> None:
    unique = uuid.uuid4().hex[:8]
    content = f"# Office Guide\n\n## Parking\n\nVisitor parking code {unique} is valid on weekdays."
    upload = await client.post(
        "/api/documents",
        headers=admin_headers,
        files=markdown_file(content),
        data={"title": "Office Guide"},
    )
    assert upload.status_code == 201, upload.text
    document = upload.json()
    assert document["status"] == "pending" and document["source_type"] == "markdown"

    detail = await wait_for_status(client, admin_headers, document["id"], "indexed")
    assert detail["status"] == "indexed" and detail["chunk_count"] == 1

    chunks = await client.get(f"/api/documents/{document['id']}/chunks", headers=admin_headers)
    assert chunks.json()["items"][0]["section"] == "Parking"

    search = await client.get(
        "/api/knowledge/search",
        headers=admin_headers,
        params={"q": f"parking code {unique}", "top_k": 3},
    )
    assert search.json()["results"][0]["document_id"] == document["id"]

    reindex = await client.post(f"/api/documents/{document['id']}/reindex", headers=admin_headers)
    assert reindex.status_code == 200
    detail = await wait_for_status(client, admin_headers, document["id"], "indexed")
    assert detail["status"] == "indexed"

    assert (
        await client.delete(f"/api/documents/{document['id']}", headers=admin_headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/documents/{document['id']}", headers=admin_headers)
    ).status_code == 404


async def test_duplicate_uploads_are_rejected(client, admin_headers) -> None:
    files = markdown_file(f"# Same\n\nIdentical content {uuid.uuid4()}.")
    assert (
        await client.post("/api/documents", headers=admin_headers, files=files)
    ).status_code == 201
    again = await client.post("/api/documents", headers=admin_headers, files=files)
    assert again.status_code == 409


async def test_file_type_and_size_are_validated(client, admin_headers) -> None:
    exe = await client.post(
        "/api/documents",
        headers=admin_headers,
        files={"file": ("tool.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert exe.status_code == 415
    fake_pdf = await client.post(
        "/api/documents",
        headers=admin_headers,
        files={"file": ("report.pdf", b"not a pdf", "application/pdf")},
    )
    assert fake_pdf.status_code == 415

    settings = get_settings()
    original = settings.max_upload_mb
    settings.max_upload_mb = 1
    try:
        big = await client.post(
            "/api/documents", headers=admin_headers, files=markdown_file("a" * (1024 * 1024 + 10))
        )
        assert big.status_code == 413
    finally:
        settings.max_upload_mb = original


async def test_unparseable_documents_are_marked_failed(client, admin_headers) -> None:
    upload = await client.post(
        "/api/documents",
        headers=admin_headers,
        files={"file": ("broken.pdf", b"%PDF-1.4 broken " + uuid.uuid4().bytes, "application/pdf")},
    )
    assert upload.status_code == 201
    detail = await wait_for_status(client, admin_headers, upload.json()["id"], "failed")
    assert detail["status"] == "failed"
    assert "PDF" in detail["error"]
