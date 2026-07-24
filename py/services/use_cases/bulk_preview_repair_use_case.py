"""Bulk repair of missing local model previews."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional

from ...utils.constants import PREVIEW_EXTENSIONS
from ...utils.file_utils import find_preview_file

ProgressCallback = Callable[[Dict[str, object]], Awaitable[None]]


class BulkPreviewRepairUseCase:
    """Restore missing preview files without refreshing unrelated metadata."""

    def __init__(
        self,
        *,
        service,
        metadata_sync,
        preview_service,
        metadata_manager,
        logger: Optional[logging.Logger] = None,
        concurrency: int = 3,
        download_timeout_seconds: float = 60.0,
        download_attempts: int = 2,
    ) -> None:
        self._service = service
        self._scanner = service.scanner
        self._metadata_sync = metadata_sync
        self._preview_service = preview_service
        self._metadata_manager = metadata_manager
        self._logger = logger or logging.getLogger(__name__)
        self._concurrency = max(1, int(concurrency))
        self._download_timeout_seconds = max(
            0.01, float(download_timeout_seconds)
        )
        self._download_attempts = max(1, int(download_attempts))

    async def execute(
        self,
        file_paths: Optional[Iterable[str]] = None,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        """Repair selected models, or all missing previews when no selection exists."""

        self._scanner.reset_cancellation()
        cache = await self._scanner.get_cached_data()
        selected = None if file_paths is None else set(file_paths)
        entries = [
            dict(item)
            for item in getattr(cache, "raw_data", [])
            if selected is None or item.get("file_path") in selected
        ]

        if progress_callback is not None:
            await progress_callback(
                {
                    "status": "scanning",
                    "scanned": 0,
                    "scan_total": len(entries),
                }
            )

        candidates: list[Dict[str, object]] = []
        already_valid = 0
        for index, entry in enumerate(entries, start=1):
            file_path = str(entry.get("file_path") or "")
            payload = await self._load_payload(file_path)
            existing_preview = self._resolve_existing_preview(file_path, entry, payload)
            entry_preview = self._valid_path(entry.get("preview_url"))
            payload_preview = self._valid_path(payload.get("preview_url"))

            if entry_preview and payload_preview:
                already_valid += 1
            else:
                candidates.append(
                    {
                        "entry": entry,
                        "payload": payload,
                        "existing_preview": existing_preview,
                    }
                )

            if progress_callback is not None and (
                index == len(entries) or index % 50 == 0
            ):
                await progress_callback(
                    {
                        "status": "scanning",
                        "scanned": index,
                        "scan_total": len(entries),
                    }
                )

        total = len(candidates)
        counts: Counter[str] = Counter()
        failures: list[Dict[str, str]] = []
        cache_updates: list[tuple[str, str, int]] = []
        completed = 0
        result_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(self._concurrency)

        if progress_callback is not None:
            await progress_callback(
                {
                    "status": "started",
                    "completed": 0,
                    "total": total,
                    "already_valid": already_valid,
                }
            )

        async def process(candidate: Dict[str, object]) -> None:
            nonlocal completed
            if self._scanner.is_cancelled():
                return

            entry = candidate["entry"]
            file_name = str(entry.get("file_name") or "")
            async with semaphore:
                if self._scanner.is_cancelled():
                    return
                if progress_callback is not None:
                    await progress_callback(
                        {
                            "status": "processing",
                            "completed": completed,
                            "total": total,
                            "current_name": file_name,
                            "downloaded": counts["downloaded"],
                            "relinked": counts["relinked"],
                            "no_remote_media": counts["no_remote_media"],
                            "failed": counts["failed"],
                        }
                    )
                try:
                    outcome = await self._repair_candidate(candidate)
                except Exception as exc:  # pragma: no cover - defensive isolation
                    self._logger.warning(
                        "Preview repair failed for %s: %s",
                        entry.get("file_path"),
                        exc,
                    )
                    outcome = {
                        "status": "failed",
                        "error": str(exc),
                    }

            async with result_lock:
                status = str(outcome["status"])
                counts[status] += 1
                completed += 1
                preview_url = str(outcome.get("preview_url") or "")
                if preview_url:
                    cache_updates.append(
                        (
                            str(entry.get("file_path") or ""),
                            preview_url,
                            int(outcome.get("preview_nsfw_level") or 0),
                        )
                    )
                if outcome.get("error"):
                    failures.append(
                        {
                            "file_name": file_name,
                            "file_path": str(entry.get("file_path") or ""),
                            "error": str(outcome["error"]),
                        }
                    )
                progress = {
                    "status": "processing",
                    "completed": completed,
                    "total": total,
                    "current_name": file_name,
                    "downloaded": counts["downloaded"],
                    "relinked": counts["relinked"],
                    "no_remote_media": counts["no_remote_media"],
                    "failed": counts["failed"],
                }

            if progress_callback is not None:
                await progress_callback(progress)

        await asyncio.gather(*(process(candidate) for candidate in candidates))

        if cache_updates:
            await self._scanner.update_previews_in_cache(cache_updates)

        cancelled = self._scanner.is_cancelled()
        status = "cancelled" if cancelled else "completed"
        result: Dict[str, object] = {
            "success": not cancelled,
            "status": status,
            "scanned": len(entries),
            "candidate_total": total,
            "processed": completed,
            "already_valid": already_valid,
            "downloaded": counts["downloaded"],
            "relinked": counts["relinked"],
            "no_remote_media": counts["no_remote_media"],
            "failed": counts["failed"],
            "failures": failures,
        }

        if progress_callback is not None:
            await progress_callback(
                {
                    **result,
                    "status": status,
                    "completed": completed,
                    "total": total,
                }
            )
        return result

    async def _repair_candidate(
        self, candidate: Dict[str, object]
    ) -> Dict[str, object]:
        entry = candidate["entry"]
        payload = candidate["payload"]
        file_path = str(entry.get("file_path") or "")
        if not file_path or not os.path.isfile(file_path):
            return {"status": "failed", "error": "Model file is missing"}

        existing_preview = str(candidate.get("existing_preview") or "")
        if existing_preview:
            return await self._persist_preview(
                file_path, payload, existing_preview, status="relinked"
            )

        images = self._extract_images(payload)
        if not images:
            sha256 = str(payload.get("sha256") or entry.get("sha256") or "").strip()
            if not sha256:
                return {
                    "status": "failed",
                    "error": "Missing SHA256; refresh model metadata first",
                }
            remote, error = await self._metadata_sync.fetch_metadata_by_sha(sha256)
            if not remote:
                return {
                    "status": "failed",
                    "error": error or "Model was not found by SHA256",
                }
            images = self._extract_images(remote)

        if not images:
            return {
                "status": "no_remote_media",
                "error": "The matched model version has no preview media",
            }

        metadata_path = os.path.splitext(file_path)[0] + ".metadata.json"
        for _attempt in range(self._download_attempts):
            downloaded = await self._preview_service.ensure_preview_for_metadata(
                metadata_path,
                payload,
                images,
                timeout_seconds=self._download_timeout_seconds,
            )
            preview_url = self._valid_path(payload.get("preview_url"))
            if downloaded and preview_url:
                return await self._persist_preview(
                    file_path, payload, preview_url, status="downloaded"
                )
            self._remove_failed_preview_files(file_path)
            payload.pop("preview_url", None)

        return {
            "status": "failed",
            "error": (
                f"Preview download failed after {self._download_attempts} attempts"
            ),
        }

    async def _persist_preview(
        self,
        file_path: str,
        payload: Dict[str, object],
        preview_url: str,
        *,
        status: str,
    ) -> Dict[str, object]:
        normalized = preview_url.replace(os.sep, "/")
        payload["preview_url"] = normalized
        nsfw_level = int(payload.get("preview_nsfw_level") or 0)
        payload["preview_nsfw_level"] = nsfw_level
        await self._metadata_manager.save_metadata(file_path, payload)
        return {
            "status": status,
            "preview_url": normalized,
            "preview_nsfw_level": nsfw_level,
        }

    async def _load_payload(self, file_path: str) -> Dict[str, object]:
        if not file_path:
            return {}
        payload = await self._metadata_manager.load_metadata_payload(file_path)
        return dict(payload) if isinstance(payload, Mapping) else {}

    def _resolve_existing_preview(
        self,
        file_path: str,
        entry: Mapping[str, object],
        payload: Mapping[str, object],
    ) -> str:
        for value in (entry.get("preview_url"), payload.get("preview_url")):
            valid = self._valid_path(value)
            if valid:
                return valid
        if not file_path:
            return ""
        stem = os.path.splitext(os.path.basename(file_path))[0]
        return self._valid_path(find_preview_file(stem, os.path.dirname(file_path)))

    @staticmethod
    def _valid_path(value: object) -> str:
        if not isinstance(value, str) or not value:
            return ""
        try:
            if os.path.isfile(value) and os.path.getsize(value) > 0:
                return value.replace(os.sep, "/")
        except OSError:
            return ""
        return ""

    @staticmethod
    def _extract_images(payload: Mapping[str, object]) -> list[Dict[str, object]]:
        civitai = payload.get("civitai")
        if isinstance(civitai, Mapping):
            images = civitai.get("images")
            if isinstance(images, list):
                return [item for item in images if isinstance(item, dict)]
        images = payload.get("images")
        if isinstance(images, list):
            return [item for item in images if isinstance(item, dict)]
        return []

    @staticmethod
    def _remove_failed_preview_files(file_path: str) -> None:
        """Remove partial files left behind by interrupted preview transfers."""

        stem = os.path.splitext(os.path.basename(file_path))[0]
        directory = os.path.dirname(file_path)
        for extension in PREVIEW_EXTENSIONS:
            candidate = os.path.join(directory, stem + extension)
            if not os.path.isfile(candidate):
                continue
            try:
                os.remove(candidate)
            except OSError:
                pass
