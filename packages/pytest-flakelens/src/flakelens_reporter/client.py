"""HTTP client for the FlakeLens ingestion API.

Reporting must never break a test session: every call is wrapped, and the
first network failure disables the client for the rest of the session with a
single warning.
"""
import sys
from pathlib import Path

import httpx


class FlakelensClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.disabled = False
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"X-Api-Key": api_key},
            timeout=timeout,
            transport=httpx.HTTPTransport(retries=2),
        )

    def _warn_and_disable(self, action: str, exc: Exception) -> None:
        self.disabled = True
        print(
            f"\n[flakelens] WARNING: {action} failed ({exc!r}) - "
            "reporting disabled for the rest of this session.",
            file=sys.stderr,
        )

    def create_run(self, payload: dict) -> bool:
        if self.disabled:
            return False
        try:
            response = self._http.post("/api/v1/ingest/runs", json=payload)
            response.raise_for_status()
            return True
        except Exception as exc:
            self._warn_and_disable("creating run", exc)
            return False

    def post_results(self, run_uuid: str, envelopes: list[dict]) -> dict:
        """Returns result_ref -> result_id, or {} on failure."""
        if self.disabled or not envelopes:
            return {}
        try:
            response = self._http.post(
                f"/api/v1/ingest/runs/{run_uuid}/results", json={"results": envelopes}
            )
            response.raise_for_status()
            return response.json().get("results", {})
        except Exception as exc:
            self._warn_and_disable("posting results", exc)
            return {}

    def upload_artifact(
        self, run_uuid: str, result_id: int, attempt_index: int, kind: str, path: Path
    ) -> None:
        if self.disabled:
            return
        try:
            with open(path, "rb") as fileobj:
                response = self._http.post(
                    f"/api/v1/ingest/runs/{run_uuid}/results/{result_id}/artifacts",
                    data={"attempt_index": str(attempt_index), "kind": kind},
                    files={"file": (path.name, fileobj)},
                )
            response.raise_for_status()
        except FileNotFoundError:
            pass  # artifact was cleaned up between discovery and upload
        except Exception as exc:
            self._warn_and_disable(f"uploading artifact {path.name}", exc)

    def finish_run(self, run_uuid: str) -> dict:
        if self.disabled:
            return {}
        try:
            response = self._http.post(f"/api/v1/ingest/runs/{run_uuid}/finish", json={})
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            self._warn_and_disable("finishing run", exc)
            return {}

    def close(self) -> None:
        self._http.close()
