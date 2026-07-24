"""Tests for repairing missing model previews."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Dict

import pytest

from py.services.use_cases.bulk_preview_repair_use_case import (
    BulkPreviewRepairUseCase,
)


class StubScanner:
    def __init__(self, entries):
        self.cache = SimpleNamespace(raw_data=entries)
        self.cancelled = False
        self.cache_updates = []

    async def get_cached_data(self):
        return self.cache

    def reset_cancellation(self):
        self.cancelled = False

    def is_cancelled(self):
        return self.cancelled

    async def update_previews_in_cache(self, updates):
        self.cache_updates.extend(updates)
        return len(updates)


class StubMetadataManager:
    def __init__(self, payloads=None):
        self.payloads = payloads or {}
        self.saved = []

    async def load_metadata_payload(self, file_path):
        return dict(self.payloads.get(file_path, {}))

    async def save_metadata(self, file_path, payload):
        self.saved.append((file_path, dict(payload)))
        return True


class StubMetadataSync:
    def __init__(self, remote=None, error=None):
        self.remote = remote
        self.error = error
        self.hashes = []

    async def fetch_metadata_by_sha(self, sha256):
        self.hashes.append(sha256)
        return self.remote, self.error


class StubPreviewService:
    def __init__(self, *, succeeds=True):
        self.succeeds = succeeds
        self.calls = []

    async def ensure_preview_for_metadata(
        self,
        metadata_path,
        payload,
        images,
        *,
        timeout_seconds=None,
    ):
        self.calls.append((metadata_path, images, timeout_seconds))
        if not self.succeeds:
            return False
        preview_path = str(Path(metadata_path).with_suffix("").with_suffix(".webp"))
        Path(preview_path).write_bytes(b"preview")
        payload["preview_url"] = preview_path
        payload["preview_nsfw_level"] = 2
        return True


def build_use_case(
    entries,
    *,
    payloads=None,
    remote=None,
    preview_service=None,
):
    scanner = StubScanner(entries)
    service = SimpleNamespace(scanner=scanner)
    metadata_manager = StubMetadataManager(payloads)
    metadata_sync = StubMetadataSync(remote)
    preview = preview_service or StubPreviewService()
    use_case = BulkPreviewRepairUseCase(
        service=service,
        metadata_sync=metadata_sync,
        preview_service=preview,
        metadata_manager=metadata_manager,
        concurrency=2,
        download_timeout_seconds=45,
    )
    return use_case, scanner, metadata_manager, metadata_sync, preview


def create_model(tmp_path: Path, name: str) -> str:
    model_path = tmp_path / f"{name}.safetensors"
    model_path.write_bytes(b"model")
    return str(model_path)


@pytest.mark.asyncio
async def test_downloads_from_cached_civitai_images(tmp_path):
    model_path = create_model(tmp_path, "cached")
    payloads = {
        model_path: {
            "sha256": "abc",
            "civitai": {
                "images": [
                    {
                        "url": "https://example.test/preview.jpg",
                        "type": "image",
                    }
                ]
            },
        }
    }
    entries = [
        {
            "file_path": model_path,
            "file_name": "cached.safetensors",
            "sha256": "abc",
            "preview_url": "",
        }
    ]
    use_case, scanner, metadata_manager, metadata_sync, preview = build_use_case(
        entries, payloads=payloads
    )

    result = await use_case.execute()

    assert result["downloaded"] == 1
    assert result["failed"] == 0
    assert metadata_sync.hashes == []
    assert preview.calls[0][2] == 45
    assert len(metadata_manager.saved) == 1
    assert len(scanner.cache_updates) == 1


@pytest.mark.asyncio
async def test_fetches_media_by_hash_only_when_not_cached(tmp_path):
    model_path = create_model(tmp_path, "remote")
    entries = [
        {
            "file_path": model_path,
            "file_name": "remote.safetensors",
            "sha256": "remote-hash",
            "preview_url": "",
        }
    ]
    remote = {
        "images": [
            {
                "url": "https://example.test/remote.mp4",
                "type": "video",
            }
        ]
    }
    use_case, _scanner, _manager, metadata_sync, preview = build_use_case(
        entries, remote=remote
    )

    result = await use_case.execute()

    assert result["downloaded"] == 1
    assert metadata_sync.hashes == ["remote-hash"]
    assert preview.calls[0][1] == remote["images"]


@pytest.mark.asyncio
async def test_relinks_existing_sibling_without_network(tmp_path):
    model_path = create_model(tmp_path, "local")
    preview_path = tmp_path / "local.png"
    preview_path.write_bytes(b"preview")
    entries = [
        {
            "file_path": model_path,
            "file_name": "local.safetensors",
            "sha256": "abc",
            "preview_url": "",
        }
    ]
    use_case, scanner, metadata_manager, metadata_sync, preview = build_use_case(
        entries
    )

    result = await use_case.execute()

    assert result["relinked"] == 1
    assert result["downloaded"] == 0
    assert metadata_sync.hashes == []
    assert preview.calls == []
    assert metadata_manager.saved[0][1]["preview_url"] == str(preview_path)
    assert scanner.cache_updates[0][1] == str(preview_path)


@pytest.mark.asyncio
async def test_selected_paths_do_not_scan_unselected_models(tmp_path):
    selected_path = create_model(tmp_path, "selected")
    other_path = create_model(tmp_path, "other")
    entries = [
        {
            "file_path": selected_path,
            "file_name": "selected.safetensors",
            "sha256": "selected",
            "preview_url": "",
        },
        {
            "file_path": other_path,
            "file_name": "other.safetensors",
            "sha256": "other",
            "preview_url": "",
        },
    ]
    remote = {
        "images": [{"url": "https://example.test/image.jpg", "type": "image"}]
    }
    use_case, _scanner, _manager, metadata_sync, _preview = build_use_case(
        entries, remote=remote
    )

    result = await use_case.execute([selected_path])

    assert result["scanned"] == 1
    assert result["candidate_total"] == 1
    assert metadata_sync.hashes == ["selected"]


@pytest.mark.asyncio
async def test_reports_version_without_remote_media_separately(tmp_path):
    model_path = create_model(tmp_path, "no-media")
    entries = [
        {
            "file_path": model_path,
            "file_name": "no-media.safetensors",
            "sha256": "no-media",
            "preview_url": "",
        }
    ]
    use_case, _scanner, _manager, _sync, _preview = build_use_case(
        entries, remote={"images": []}
    )

    result = await use_case.execute()

    assert result["no_remote_media"] == 1
    assert result["failed"] == 0
    assert result["failures"][0]["error"] == (
        "The matched model version has no preview media"
    )
