"""Loopback-only client for Hermes Gateway's approval-aware Runs API."""

import json
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path


RUN_ID = re.compile(r"run_[0-9a-f]{32}\Z")


class HermesRunsClient:
    def __init__(self, key_file: Path, base_url: str = "http://127.0.0.1:8642"):
        self.key_file = key_file
        self.base_url = base_url.rstrip("/")
        if self.base_url != "http://127.0.0.1:8642":
            raise ValueError("Hermes Runs API must use the local Gateway listener")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, method: str, path: str, body: dict | None = None,
                 timeout: float = 10, extra_headers: dict | None = None) -> dict:
        key = self.key_file.read_text(encoding="utf-8").strip()
        if len(key) < 16:
            raise RuntimeError("Hermes API key is missing or too short")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(self.base_url + path, data=data,
                                         headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Hermes API returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Hermes API unavailable: {type(exc).__name__}") from None

    def capabilities(self) -> dict:
        return self._request("GET", "/v1/capabilities")

    def start_run(self, text: str, session_id: str | None) -> str:
        body = {"input": text}
        if session_id:
            body["session_id"] = session_id
        result = self._request("POST", "/v1/runs", body,
                               extra_headers={"Idempotency-Key": uuid.uuid4().hex})
        run_id = result.get("run_id", "")
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise RuntimeError("Hermes API returned an invalid run ID")
        return run_id

    def status(self, run_id: str) -> dict:
        self._validate_run_id(run_id)
        return self._request("GET", f"/v1/runs/{run_id}")

    def approve(self, run_id: str, request_id: str, choice: str) -> dict:
        self._validate_run_id(run_id)
        if choice not in {"once", "deny"}:
            raise ValueError("Only one-time approval or denial is allowed")
        if not request_id or len(request_id) > 256:
            raise ValueError("Invalid approval request ID")
        return self._request("POST", f"/v1/runs/{run_id}/approval",
                             {"request_id": request_id, "choice": choice})

    def stop(self, run_id: str) -> None:
        self._validate_run_id(run_id)
        self._request("POST", f"/v1/runs/{run_id}/stop", {})

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid Hermes run ID")
