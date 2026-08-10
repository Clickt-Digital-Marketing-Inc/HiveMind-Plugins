#!/usr/bin/env python3
"""Thin CM3 protected-compute client helpers.

This module deliberately contains no CSV parser, CM3 formula, findings engine,
renderer, or local execution fallback.  CSV bytes are read only by the local
hashing loop and the direct PUT transport; MCP calls receive metadata and
assumptions only.

The agent-facing skill drives the MCP tools.  ``run_fixture_workflow`` exists
for deterministic contract testing with injected transports and is not a
second compute path.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import re
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping
from urllib.parse import urlsplit


CONTRACT_VERSION = "1.0"
MAX_FILE_BYTES = 26_214_400
REQUIRED_FILE_ROLES = ("google_ads_shopping",)
OPTIONAL_FILE_ROLES = ("shopify_gross_profit",)
ALLOWED_FILE_ROLES = frozenset(REQUIRED_FILE_ROLES + OPTIONAL_FILE_ROLES)
ARTIFACT_EXPIRY_SECONDS = 3_600
UPLOAD_EXPIRY_SECONDS = 900

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ ()-]{0,122}\.csv$")
_SAFE_REQUEST_ID = re.compile(r"^req_[A-Za-z0-9_-]{20,64}$")
_ARTIFACT_TYPES = (
    ("text/markdown", re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,124}\.md$")),
    ("text/html", re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,122}\.html$")),
    (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,122}\.xlsx$"),
    ),
)

_PUBLIC_ERROR_CODES = frozenset({
    "INVALID_REQUEST", "AUTH_MISSING", "AUTH_INVALID", "AUTH_REVOKED", "AUTH_EXPIRED",
    "SCOPE_DENIED", "UPLOAD_SESSION_EXPIRED", "FILE_SIZE_LIMIT_EXCEEDED",
    "FILE_SIZE_MISMATCH", "FILE_HASH_MISMATCH", "UPLOAD_INCOMPLETE", "TENANT_MISMATCH",
    "JOB_REPLAYED", "INVALID_ASSUMPTIONS", "MALFORMED_CSV", "EXECUTION_TIMEOUT",
    "QUOTA_EXCEEDED", "CONCURRENCY_LIMIT", "INTERNAL_ERROR", "ARTIFACT_EXPIRED",
    "ARTIFACT_INTEGRITY_FAILED",
})


class WorkflowError(RuntimeError):
    """A safe, operator-facing workflow error."""

    def __init__(self, code: str, guidance: str):
        super().__init__(guidance)
        self.code = code
        self.guidance = guidance


@dataclass(frozen=True)
class LocalFile:
    role: str
    path: Path
    filename: str
    byte_size: int
    sha256: str

    def metadata(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
        }


PutTransport = Callable[[str, Mapping[str, str], BinaryIO, int], None]
ToolCall = Callable[[dict[str, Any]], dict[str, Any]]


_ERROR_GUIDANCE = {
    "INVALID_REQUEST": "The request shape is invalid. Update the CM3 plugin or correct the selected file metadata, then start a new job.",
    "AUTH_MISSING": "Configure the service-issued CM3 credential in the MCP client's private secret store, then reconnect.",
    "AUTH_INVALID": "Replace the configured CM3 credential with a valid service-issued value; do not paste it into chat or logs.",
    "AUTH_REVOKED": "Ask the service administrator to issue a replacement CM3 credential, then update the private secret store.",
    "AUTH_EXPIRED": "Rotate the expired CM3 credential through the service administrator, then reconnect.",
    "SCOPE_DENIED": "Ask the service administrator to grant this credential CM3 prepare-and-generate scope.",
    "UPLOAD_SESSION_EXPIRED": "The 15-minute upload session expired. Start again at cm3_prepare_uploads; do not reuse the old URLs or job ID.",
    "FILE_SIZE_LIMIT_EXCEEDED": "Each CSV must be 25 MiB or smaller. Export a narrower period or reduce the file outside the model, then retry.",
    "FILE_SIZE_MISMATCH": "The file changed after metadata was prepared. Start a new job so size and upload bytes come from the same file.",
    "FILE_HASH_MISMATCH": "The file changed or the upload was corrupted. Start a new job and upload the original local file again.",
    "UPLOAD_INCOMPLETE": "One or more required uploads are incomplete. Complete every returned PUT before generating, or start a new job if URLs expired.",
    "TENANT_MISMATCH": "This job belongs to another partner context. Reconnect with the intended CM3 credential and start a new job.",
    "JOB_REPLAYED": "This job cannot be reused with changed assumptions. Start a new prepare/upload/generate sequence.",
    "INVALID_ASSUMPTIONS": "Correct the percentages, non-negative fixed costs, and strictly descending band thresholds, then start a new job.",
    "MALFORMED_CSV": "Export a fresh supported Google Ads Shopping CSV (and Shopify Gross profit by product CSV if used), then start a new job.",
    "EXECUTION_TIMEOUT": "Generation exceeded the service limit. Start a new job; if it repeats, share only the safe request ID with support.",
    "QUOTA_EXCEEDED": "The completed-job quota is exhausted. Wait for the rolling quota window to reopen, then start a new job.",
    "CONCURRENCY_LIMIT": "Another job is already running. Wait for it to finish, then start a new job.",
    "INTERNAL_ERROR": "The service failed safely. Retry with a new job; if it repeats, share only the safe request ID with support.",
    "ARTIFACT_EXPIRED": "The report link expired after one hour. Generate a new report; expired URLs cannot be refreshed.",
    "ARTIFACT_INTEGRITY_FAILED": "Do not use the artifact. Generate a new report; if it repeats, share only the safe request ID with support.",
    "NETWORK_ERROR": "The remote request could not be completed. Check MCP connectivity or outbound HTTPS access and retry without sharing credentials or signed URLs.",
    "UPLOAD_HTTP_ERROR": "A direct upload failed. Check outbound HTTPS access, then start a new job because the upload session may no longer be safe to reuse.",
    "CONTRACT_VERSION_MISMATCH": "The service contract is incompatible with this plugin. Stop before upload and update either the service or plugin to CM3 contract 1.0.",
    "ARTIFACT_EXPIRY_INVALID": "The service returned invalid or expired artifact metadata. Do not present or download the links; generate a new report.",
    "REMOTE_ERROR_INVALID": "The CM3 service returned an unsupported or malformed error. Stop and share only the safe request ID with support.",
    "UPLOAD_HEADERS_INVALID": "The upload instructions contain invalid HTTP headers. Do not upload; start a new job and share only the safe request ID with support if it repeats.",
    "UPLOAD_URL_INVALID": "The upload instructions contain an invalid HTTPS URL. Do not upload; start a new job and share only the safe request ID with support if it repeats.",
}


def _safe_error(code: str) -> WorkflowError:
    safe_code = code if code in _ERROR_GUIDANCE else "REMOTE_ERROR_INVALID"
    return WorkflowError(safe_code, _ERROR_GUIDANCE[safe_code])


def _parse_time(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str):
        raise _safe_error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _safe_error(code) from None
    if parsed.tzinfo is None:
        raise _safe_error(code)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_contract_version(payload: Mapping[str, Any]) -> None:
    """Fail closed before any upload or response presentation."""
    if not isinstance(payload, Mapping) or payload.get("contract_version") != CONTRACT_VERSION:
        raise _safe_error("CONTRACT_VERSION_MISMATCH")


def _valid_https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        if not value or any(ord(character) < 0x21 or ord(character) > 0x7e for character in value):
            return False
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port  # Access is validation: malformed ports raise ValueError.
        return bool(
            parsed.scheme == "https"
            and hostname
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
        )
    except (TypeError, ValueError, UnicodeError):
        return False


def _validated_upload_headers(headers: Any) -> dict[str, str]:
    """Copy contract headers only after strict, log-safe HTTP validation."""
    try:
        if not isinstance(headers, Mapping) or not 1 <= len(headers) <= 8:
            raise ValueError
        items = list(headers.items())
        if not all(
            isinstance(key, str)
            and re.fullmatch(r"[a-z0-9-]{1,64}", key)
            and isinstance(value, str)
            and re.fullmatch(r"[\x20-\x7e]{1,512}", value)
            for key, value in items
        ):
            raise ValueError
        return dict(items)
    except (TypeError, ValueError, UnicodeError):
        raise _safe_error("UPLOAD_HEADERS_INVALID") from None


def _validate_roles(paths: Mapping[str, str | Path]) -> None:
    roles = set(paths)
    unknown = roles - ALLOWED_FILE_ROLES
    missing = set(REQUIRED_FILE_ROLES) - roles
    if unknown or missing:
        raise _safe_error("INVALID_REQUEST")


def inspect_local_files(paths: Mapping[str, str | Path]) -> dict[str, LocalFile]:
    """Stream file metadata locally without decoding or returning CSV rows."""
    _validate_roles(paths)
    inspected: dict[str, LocalFile] = {}
    for role in REQUIRED_FILE_ROLES + OPTIONAL_FILE_ROLES:
        if role not in paths:
            continue
        path = Path(paths[role]).expanduser()
        filename = path.name
        if not _SAFE_FILENAME.fullmatch(filename) or not path.is_file():
            raise _safe_error("INVALID_REQUEST")
        byte_size = path.stat().st_size
        if byte_size < 1:
            raise _safe_error("INVALID_REQUEST")
        if byte_size > MAX_FILE_BYTES:
            raise _safe_error("FILE_SIZE_LIMIT_EXCEEDED")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        inspected[role] = LocalFile(
            role=role,
            path=path,
            filename=filename,
            byte_size=byte_size,
            sha256=digest.hexdigest(),
        )
    return inspected


def build_prepare_request(files: Mapping[str, LocalFile]) -> dict[str, Any]:
    _validate_roles(files)
    return {
        "contract_version": CONTRACT_VERSION,
        "files": {role: files[role].metadata() for role in REQUIRED_FILE_ROLES + OPTIONAL_FILE_ROLES if role in files},
    }


def validate_assumptions(assumptions: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "cogs_pct", "ship_pct", "proc_pct", "fixed_costs",
        "band_exc", "band_high", "band_avg", "band_low",
    )
    allowed = set(required) | {"period"}
    if set(assumptions) - allowed or any(key not in assumptions for key in required):
        raise _safe_error("INVALID_ASSUMPTIONS")
    result: dict[str, Any] = {}
    for key in required:
        value = assumptions[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _safe_error("INVALID_ASSUMPTIONS")
        result[key] = value
    if not all(0 <= result[key] <= 100 for key in ("cogs_pct", "ship_pct", "proc_pct")):
        raise _safe_error("INVALID_ASSUMPTIONS")
    if not 0 <= result["fixed_costs"] <= 1_000_000_000_000:
        raise _safe_error("INVALID_ASSUMPTIONS")
    bands = [result[key] for key in ("band_exc", "band_high", "band_avg", "band_low")]
    if not all(-10 <= value <= 10 for value in bands) or not all(a > b for a, b in zip(bands, bands[1:])):
        raise _safe_error("INVALID_ASSUMPTIONS")
    if "period" in assumptions:
        period = assumptions["period"]
        if not isinstance(period, str) or not 1 <= len(period) <= 128:
            raise _safe_error("INVALID_ASSUMPTIONS")
        result["period"] = period
    return result


def build_generate_request(job_id: Any, assumptions: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(job_id, str) or not re.fullmatch(r"job_[A-Za-z0-9_-]{20,64}", job_id):
        raise _safe_error("INVALID_REQUEST")
    return {"contract_version": CONTRACT_VERSION, "job_id": job_id, **validate_assumptions(assumptions)}


def _validate_upload_response(
    response: Mapping[str, Any], files: Mapping[str, LocalFile], now: datetime
) -> Mapping[str, Mapping[str, Any]]:
    validate_contract_version(response)
    if set(response) != {
        "contract_version", "request_id", "job_id", "upload_expires_at",
        "upload_expiry_seconds", "uploads",
    }:
        raise _safe_error("INVALID_REQUEST")
    if not isinstance(response.get("request_id"), str) or not _SAFE_REQUEST_ID.fullmatch(response["request_id"]):
        raise _safe_error("INVALID_REQUEST")
    if not isinstance(response.get("job_id"), str) or not re.fullmatch(r"job_[A-Za-z0-9_-]{20,64}", response["job_id"]):
        raise _safe_error("INVALID_REQUEST")
    if response.get("upload_expiry_seconds") != UPLOAD_EXPIRY_SECONDS:
        raise _safe_error("INVALID_REQUEST")
    if _parse_time(response.get("upload_expires_at"), code="UPLOAD_SESSION_EXPIRED") <= now:
        raise _safe_error("UPLOAD_SESSION_EXPIRED")
    uploads = response.get("uploads")
    if not isinstance(uploads, Mapping) or set(uploads) != set(files):
        raise _safe_error("INVALID_REQUEST")
    for role, local in files.items():
        instruction = uploads.get(role)
        if not isinstance(instruction, Mapping):
            raise _safe_error("INVALID_REQUEST")
        if set(instruction) != {"filename", "put_url", "required_headers", "expires_at"}:
            raise _safe_error("INVALID_REQUEST")
        if instruction.get("filename") != local.filename:
            raise _safe_error("INVALID_REQUEST")
        url = instruction.get("put_url")
        headers = instruction.get("required_headers")
        if not _valid_https_url(url):
            raise _safe_error("UPLOAD_URL_INVALID")
        _validated_upload_headers(headers)
        if _parse_time(instruction.get("expires_at"), code="UPLOAD_SESSION_EXPIRED") <= now:
            raise _safe_error("UPLOAD_SESSION_EXPIRED")
    return uploads


def upload_files(
    files: Mapping[str, LocalFile],
    prepare_response: Mapping[str, Any],
    put: PutTransport,
    *,
    now: datetime | None = None,
) -> None:
    """PUT each local file as an opaque raw body with exact returned headers."""
    current = (now or _utc_now()).astimezone(timezone.utc)
    uploads = _validate_upload_response(prepare_response, files, current)
    for role in REQUIRED_FILE_ROLES + OPTIONAL_FILE_ROLES:
        if role not in files:
            continue
        instruction = uploads[role]
        local = files[role]
        headers = _validated_upload_headers(instruction["required_headers"])
        with local.path.open("rb") as body:
            try:
                put(
                    str(instruction["put_url"]),
                    headers,
                    body,
                    local.byte_size,
                )
            except WorkflowError:
                raise
            except (OSError, TimeoutError):
                raise _safe_error("NETWORK_ERROR") from None


def direct_https_put(
    url: str,
    headers: Mapping[str, str],
    body: BinaryIO,
    byte_size: int,
    *,
    timeout: float = 60.0,
) -> None:
    """Stream one raw file body directly to an HTTPS URL without logging it."""
    connection: http.client.HTTPSConnection | None = None
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise _safe_error("UPLOAD_HTTP_ERROR")
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        safe_headers = _validated_upload_headers(headers)
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port or 443,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        connection.putrequest("PUT", target, skip_accept_encoding=True)
        lower_headers = {key.lower() for key in safe_headers}
        for key, value in safe_headers.items():
            connection.putheader(key, value)
        if "content-length" not in lower_headers:
            connection.putheader("content-length", str(byte_size))
        connection.endheaders()
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            connection.send(chunk)
        response = connection.getresponse()
        response.read()
        if not 200 <= response.status < 300:
            raise _safe_error("UPLOAD_HTTP_ERROR")
    except WorkflowError:
        raise
    except (OSError, http.client.HTTPException, TypeError, ValueError, UnicodeError):
        raise _safe_error("UPLOAD_HTTP_ERROR") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException, TypeError, ValueError, UnicodeError):
                pass


def raise_for_tool_error(payload: Mapping[str, Any]) -> None:
    """Convert a public MCP error to static guidance without echoing its message."""
    validate_contract_version(payload)
    error = payload.get("error")
    if not isinstance(error, Mapping):
        raise _safe_error("REMOTE_ERROR_INVALID")
    code = error.get("code")
    if not isinstance(code, str) or code not in _PUBLIC_ERROR_CODES:
        raise _safe_error("REMOTE_ERROR_INVALID")
    raise _safe_error(code)


def validate_generate_response(response: Mapping[str, Any], *, now: datetime | None = None) -> None:
    validate_contract_version(response)
    if "error" in response:
        raise_for_tool_error(response)
    if set(response) != {"contract_version", "request_id", "job_id", "headline_metrics", "artifacts"}:
        raise _safe_error("INVALID_REQUEST")
    if not isinstance(response.get("request_id"), str) or not _SAFE_REQUEST_ID.fullmatch(response["request_id"]):
        raise _safe_error("INVALID_REQUEST")
    if not isinstance(response.get("job_id"), str) or not re.fullmatch(r"job_[A-Za-z0-9_-]{20,64}", response["job_id"]):
        raise _safe_error("INVALID_REQUEST")
    current = (now or _utc_now()).astimezone(timezone.utc)
    metrics = response.get("headline_metrics")
    artifacts = response.get("artifacts")
    if not isinstance(metrics, Mapping) or not isinstance(artifacts, list) or len(artifacts) != 3:
        raise _safe_error("INVALID_REQUEST")
    if set(metrics) != {
        "currency", "product_count", "revenue", "ad_spend", "cm3", "cm3_pct",
        "roas", "excellent_count", "poor_count",
    }:
        raise _safe_error("INVALID_REQUEST")
    if not isinstance(metrics["currency"], str) or not re.fullmatch(r"[A-Z]{3}", metrics["currency"]):
        raise _safe_error("INVALID_REQUEST")
    for key in ("product_count", "excellent_count", "poor_count"):
        if isinstance(metrics[key], bool) or not isinstance(metrics[key], int) or metrics[key] < 0:
            raise _safe_error("INVALID_REQUEST")
    for key in ("revenue", "ad_spend", "cm3"):
        if isinstance(metrics[key], bool) or not isinstance(metrics[key], (int, float)) or not math.isfinite(metrics[key]):
            raise _safe_error("INVALID_REQUEST")
    for key in ("cm3_pct", "roas"):
        if metrics[key] is not None and (
            isinstance(metrics[key], bool)
            or not isinstance(metrics[key], (int, float))
            or not math.isfinite(metrics[key])
        ):
            raise _safe_error("INVALID_REQUEST")
    for artifact, (mime_type, filename_pattern) in zip(artifacts, _ARTIFACT_TYPES):
        if not isinstance(artifact, Mapping):
            raise _safe_error("INVALID_REQUEST")
        if set(artifact) != {
            "filename", "mime_type", "byte_size", "sha256", "download_url",
            "expires_at", "expiry_seconds",
        }:
            raise _safe_error("INVALID_REQUEST")
        filename = artifact.get("filename")
        url = artifact.get("download_url")
        if (
            not isinstance(filename, str)
            or not filename_pattern.fullmatch(filename)
            or artifact.get("mime_type") != mime_type
            or isinstance(artifact.get("byte_size"), bool)
            or not isinstance(artifact.get("byte_size"), int)
            or artifact["byte_size"] < 1
            or not isinstance(artifact.get("sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"])
            or artifact.get("expiry_seconds") != ARTIFACT_EXPIRY_SECONDS
            or not _valid_https_url(url)
            or _parse_time(artifact.get("expires_at"), code="ARTIFACT_EXPIRY_INVALID") <= current
        ):
            raise _safe_error("ARTIFACT_EXPIRY_INVALID")


def present_generate_response(response: Mapping[str, Any], *, now: datetime | None = None) -> str:
    """Return the contract-approved metrics and expiring artifact links only."""
    validate_generate_response(response, now=now)
    metrics = response["headline_metrics"]
    artifacts = response["artifacts"]
    lines = [
        f"Revenue: {metrics['currency']} {metrics['revenue']:,.2f}",
        f"Ad spend: {metrics['currency']} {metrics['ad_spend']:,.2f}",
        f"CM3: {metrics['currency']} {metrics['cm3']:,.2f}",
        f"CM3 weighted: {metrics['cm3_pct']:.2%}" if metrics["cm3_pct"] is not None else "CM3 weighted: not available",
        f"ROAS: {metrics['roas']:.2f}" if metrics["roas"] is not None else "ROAS: not available",
        f"Products: {metrics['product_count']} ({metrics['excellent_count']} excellent; {metrics['poor_count']} poor)",
        "Artifacts (links expire one hour after generation):",
    ]
    for artifact in artifacts:
        lines.append(f"- {artifact['filename']}: {artifact['download_url']} (expires {artifact['expires_at']})")
    lines.append("Download promptly. Do not paste signed links into support tickets or logs.")
    return "\n".join(lines)


def assert_json_has_no_raw_bytes(payload: Any) -> None:
    """Reject byte-bearing values before an MCP request crosses the boundary."""
    if isinstance(payload, (bytes, bytearray, memoryview)):
        raise _safe_error("INVALID_REQUEST")
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            assert_json_has_no_raw_bytes(key)
            assert_json_has_no_raw_bytes(value)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            assert_json_has_no_raw_bytes(value)


def run_fixture_workflow(
    paths: Mapping[str, str | Path],
    assumptions: Mapping[str, Any],
    prepare_call: ToolCall,
    generate_call: ToolCall,
    put: PutTransport,
    *,
    now: datetime | None = None,
) -> str:
    """Exercise the public remote sequence with injected contract transports."""
    files = inspect_local_files(paths)
    prepare_request = build_prepare_request(files)
    assert_json_has_no_raw_bytes(prepare_request)
    try:
        prepare_response = prepare_call(prepare_request)
    except WorkflowError:
        raise
    except (OSError, TimeoutError):
        raise _safe_error("NETWORK_ERROR") from None
    if not isinstance(prepare_response, Mapping):
        raise _safe_error("INVALID_REQUEST")
    if "error" in prepare_response:
        raise_for_tool_error(prepare_response)
    upload_files(files, prepare_response, put, now=now)
    generate_request = build_generate_request(prepare_response.get("job_id"), assumptions)
    assert_json_has_no_raw_bytes(generate_request)
    try:
        generate_response = generate_call(generate_request)
    except WorkflowError:
        raise
    except (OSError, TimeoutError):
        raise _safe_error("NETWORK_ERROR") from None
    if not isinstance(generate_response, Mapping):
        raise _safe_error("INVALID_REQUEST")
    if "error" in generate_response:
        raise_for_tool_error(generate_response)
    if generate_response.get("job_id") != prepare_response.get("job_id"):
        raise _safe_error("INVALID_REQUEST")
    return present_generate_response(generate_response, now=now)


def metadata_json(paths: Mapping[str, str | Path]) -> str:
    """Emit only the prepare request for mechanical agent/tool handoff."""
    request = build_prepare_request(inspect_local_files(paths))
    assert_json_has_no_raw_bytes(request)
    return json.dumps(request, sort_keys=True, separators=(",", ":"))


def _path_args(namespace: argparse.Namespace) -> dict[str, Path]:
    paths = {"google_ads_shopping": Path(namespace.google_ads)}
    if namespace.shopify:
        paths["shopify_gross_profit"] = Path(namespace.shopify)
    return paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local metadata/direct-upload helper for CM3 protected compute (contract 1.0)."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    metadata = commands.add_parser("metadata", help="print metadata-only cm3_prepare_uploads JSON")
    upload = commands.add_parser("upload", help="directly PUT local files using a saved prepare response")
    present = commands.add_parser("present", help="validate and safely present a saved generate response")
    for command in (metadata, upload):
        command.add_argument("--google-ads", required=True, help="local Google Ads Shopping CSV path")
        command.add_argument("--shopify", help="optional local Shopify Gross profit by product CSV path")
    upload.add_argument("--prepare-response", required=True, help="private temporary JSON file containing the exact tool response")
    present.add_argument("--generate-response", required=True, help="private temporary JSON file containing the exact tool response")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "metadata":
            print(metadata_json(_path_args(args)))
        elif args.command == "upload":
            files = inspect_local_files(_path_args(args))
            with Path(args.prepare_response).open("r", encoding="utf-8") as handle:
                response = json.load(handle)
            upload_files(files, response, direct_https_put)
            print("Uploads completed. The response file and signed URLs were not printed.")
        else:
            with Path(args.generate_response).open("r", encoding="utf-8") as handle:
                response = json.load(handle)
            print(present_generate_response(response))
    except WorkflowError as exc:
        print(f"{exc.code}: {exc.guidance}")
        return 2
    except (OSError, json.JSONDecodeError):
        error = _safe_error("INVALID_REQUEST")
        print(f"{error.code}: {error.guidance}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
