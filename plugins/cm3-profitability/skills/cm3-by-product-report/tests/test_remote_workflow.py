#!/usr/bin/env python3
"""Contract-fixture tests for the thin CM3 protected-compute workflow.

Stdlib only. Run standalone with ``python3 tests/test_remote_workflow.py`` or
collect with pytest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve()
SKILL = HERE.parents[1]
REPO = SKILL.parents[3]
sys.path.insert(0, str(SKILL))

import remote_workflow as remote  # noqa: E402


FIXTURE = json.loads((HERE.parent / "fixtures" / "cm3-remote-contract-v1.json").read_text())
NOW = datetime(2026, 8, 9, 17, 0, tzinfo=timezone.utc)
ASSUMPTIONS = {
    "cogs_pct": 65,
    "ship_pct": 20,
    "proc_pct": 2.9,
    "fixed_costs": 0,
    "band_exc": 0.1,
    "band_high": 0.05,
    "band_avg": 0,
    "band_low": -0.25,
    "period": "2026-07-01 through 2026-07-31",
}
RAW_MARKER = b"PRIVATE-CSV-BYTES,NEVER-MODEL-VISIBLE\nopaque-body\n"


def error_payload(code: str, message: str = "Bearer SECRET https://signed.invalid/?token=SECRET /private/raw.csv"):
    return {
        "contract_version": remote.CONTRACT_VERSION,
        "request_id": "req_abcdefghijklmnopqrstuv",
        "error": {"code": code, "message": message, "retryable": False},
    }


class RemoteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.google = self.root / "google-ads-shopping.csv"
        self.google.write_bytes(RAW_MARKER)

    def tearDown(self):
        self.temp.cleanup()

    def prepare_response(self, files):
        response = copy.deepcopy(FIXTURE["prepare_response"])
        item = response["uploads"]["google_ads_shopping"]
        item["required_headers"]["x-checksum-sha256"] = files["google_ads_shopping"].sha256
        return response

    def test_complete_required_fixture_sequence_keeps_raw_bytes_out_of_json_and_output(self):
        sequence = []
        requests = []
        uploaded = []

        def prepare_call(payload):
            sequence.append("prepare")
            requests.append(copy.deepcopy(payload))
            files = remote.inspect_local_files({"google_ads_shopping": self.google})
            return self.prepare_response(files)

        def put(url, headers, body, byte_size):
            sequence.append("put")
            uploaded.append((url, dict(headers), body.read(), byte_size))

        def generate_call(payload):
            sequence.append("generate")
            requests.append(copy.deepcopy(payload))
            return copy.deepcopy(FIXTURE["generate_response"])

        output = remote.run_fixture_workflow(
            {"google_ads_shopping": self.google}, ASSUMPTIONS,
            prepare_call, generate_call, put, now=NOW,
        )

        self.assertEqual(sequence, ["prepare", "put", "generate"])
        self.assertEqual(uploaded[0][2], RAW_MARKER)
        self.assertEqual(uploaded[0][3], len(RAW_MARKER))
        self.assertNotIn(str(self.google), json.dumps(requests))
        self.assertNotIn(RAW_MARKER.decode(), json.dumps(requests))
        self.assertNotIn(RAW_MARKER.decode(), output)
        self.assertIn("Revenue: USD 125,000.50", output)
        self.assertIn("links expire one hour", output)

    def test_metadata_hash_size_and_optional_role_are_derived_from_files(self):
        shopify_body = b"second opaque body\x00\xff"
        shopify = self.root / "shopify-gross-profit.csv"
        shopify.write_bytes(shopify_body)
        files = remote.inspect_local_files({
            "google_ads_shopping": self.google,
            "shopify_gross_profit": shopify,
        })
        request = remote.build_prepare_request(files)
        self.assertEqual(list(request["files"]), ["google_ads_shopping", "shopify_gross_profit"])
        self.assertEqual(request["files"]["google_ads_shopping"]["byte_size"], len(RAW_MARKER))
        self.assertEqual(
            request["files"]["google_ads_shopping"]["sha256"],
            hashlib.sha256(RAW_MARKER).hexdigest(),
        )
        self.assertEqual(request["files"]["shopify_gross_profit"]["byte_size"], len(shopify_body))
        self.assertEqual(request["files"]["shopify_gross_profit"]["sha256"], hashlib.sha256(shopify_body).hexdigest())
        self.assertNotIn("path", json.dumps(request))

    def test_required_and_optional_roles_fail_closed(self):
        with self.assertRaisesRegex(remote.WorkflowError, "request shape is invalid"):
            remote.inspect_local_files({})
        with self.assertRaisesRegex(remote.WorkflowError, "request shape is invalid"):
            remote.inspect_local_files({"google_ads_shopping": self.google, "unexpected": self.google})

        files = remote.inspect_local_files({"google_ads_shopping": self.google})
        response = self.prepare_response(files)
        response["uploads"]["shopify_gross_profit"] = copy.deepcopy(response["uploads"]["google_ads_shopping"])
        calls = []
        with self.assertRaisesRegex(remote.WorkflowError, "request shape is invalid"):
            remote.upload_files(files, response, lambda *args: calls.append(args), now=NOW)
        self.assertEqual(calls, [])

    def test_contract_version_mismatch_stops_before_upload(self):
        files = remote.inspect_local_files({"google_ads_shopping": self.google})
        response = self.prepare_response(files)
        response["contract_version"] = "2.0"
        calls = []
        with self.assertRaisesRegex(remote.WorkflowError, "Stop before upload"):
            remote.upload_files(files, response, lambda *args: calls.append(args), now=NOW)
        self.assertEqual(calls, [])

    def test_every_returned_upload_header_is_propagated_exactly(self):
        files = remote.inspect_local_files({"google_ads_shopping": self.google})
        response = self.prepare_response(files)
        expected = {
            "content-type": "text/csv",
            "x-checksum-sha256": files["google_ads_shopping"].sha256,
            "x-required-custom": "fixture-value",
        }
        response["uploads"]["google_ads_shopping"]["required_headers"] = expected
        seen = []
        remote.upload_files(files, response, lambda url, headers, body, size: seen.append(headers), now=NOW)
        self.assertEqual(seen, [expected])

    def test_raw_byte_values_are_rejected_at_mcp_json_boundary(self):
        for value in (RAW_MARKER, bytearray(RAW_MARKER), memoryview(RAW_MARKER)):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaisesRegex(remote.WorkflowError, "request shape is invalid"):
                    remote.assert_json_has_no_raw_bytes({"files": {"content": value}})

    def test_prepare_failure_never_invokes_put_generate_or_local_fallback(self):
        calls = []

        def prepare_call(_payload):
            calls.append("prepare")
            return error_payload("AUTH_MISSING")

        with self.assertRaisesRegex(remote.WorkflowError, "private secret store"):
            remote.run_fixture_workflow(
                {"google_ads_shopping": self.google}, ASSUMPTIONS,
                prepare_call,
                lambda _payload: calls.append("generate"),
                lambda *_args: calls.append("put"),
                now=NOW,
            )
        self.assertEqual(calls, ["prepare"])

        skill_text = (SKILL / "SKILL.md").read_text()
        command_text = (SKILL.parents[1] / "commands" / "cm3-report.md").read_text()
        for forbidden in ("cm3_by_product.py", "--output-md", "--output-html", "--output-xlsx", "--no-charts"):
            self.assertNotIn(forbidden, skill_text + command_text)
        self.assertIn("There is no local fallback", skill_text)
        self.assertIn("Never invoke", command_text)

        plugin_manifest = json.loads((SKILL.parents[1] / ".claude-plugin" / "plugin.json").read_text())
        marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        marketplace_entry = next(item for item in marketplace["plugins"] if item["name"] == "cm3-profitability")
        readme_cm3 = next(line for line in (REPO / "README.md").read_text().splitlines() if "**cm3-profitability**" in line)
        for description in (plugin_manifest["description"], marketplace_entry["description"], readme_cm3):
            self.assertIn("remote", description.lower())
            self.assertNotIn("pptx", description.lower())

    def test_network_failure_is_actionable_and_does_not_echo_exception(self):
        def unavailable(_payload):
            raise OSError("Bearer SECRET https://signed.invalid/?token=SECRET /private/raw.csv")

        with self.assertRaises(remote.WorkflowError) as caught:
            remote.run_fixture_workflow(
                {"google_ads_shopping": self.google}, ASSUMPTIONS,
                unavailable, lambda _payload: {}, lambda *_args: None, now=NOW,
            )
        self.assertEqual(caught.exception.code, "NETWORK_ERROR")
        self.assertIn("outbound HTTPS", caught.exception.guidance)
        self.assertNotIn("SECRET", caught.exception.guidance)
        self.assertNotIn("signed.invalid", caught.exception.guidance)

        files = remote.inspect_local_files({"google_ads_shopping": self.google})
        response = self.prepare_response(files)

        def upload_unavailable(*_args):
            raise OSError("Bearer SECRET https://upload.invalid/?token=SECRET /private/raw.csv")

        with self.assertRaises(remote.WorkflowError) as upload_caught:
            remote.upload_files(files, response, upload_unavailable, now=NOW)
        self.assertEqual(upload_caught.exception.code, "NETWORK_ERROR")
        self.assertNotIn("SECRET", upload_caught.exception.guidance)
        self.assertNotIn("upload.invalid", upload_caught.exception.guidance)

    def test_all_public_error_classes_use_static_actionable_redacted_guidance(self):
        public_codes = {
            "INVALID_REQUEST", "AUTH_MISSING", "AUTH_INVALID", "AUTH_REVOKED", "AUTH_EXPIRED",
            "SCOPE_DENIED", "UPLOAD_SESSION_EXPIRED", "FILE_SIZE_LIMIT_EXCEEDED",
            "FILE_SIZE_MISMATCH", "FILE_HASH_MISMATCH", "UPLOAD_INCOMPLETE", "TENANT_MISMATCH",
            "JOB_REPLAYED", "INVALID_ASSUMPTIONS", "MALFORMED_CSV", "EXECUTION_TIMEOUT",
            "QUOTA_EXCEEDED", "CONCURRENCY_LIMIT", "INTERNAL_ERROR", "ARTIFACT_EXPIRED",
            "ARTIFACT_INTEGRITY_FAILED",
        }
        self.assertTrue(public_codes <= set(remote._ERROR_GUIDANCE))
        reference = (SKILL / "references" / "remote-workflow.md").read_text()
        for code in public_codes:
            self.assertIn(f"`{code}`", reference)
        sensitive = ("SECRET", "signed.invalid", "/private/raw.csv", "Bearer")
        for code in sorted(public_codes):
            with self.subTest(code=code):
                with self.assertRaises(remote.WorkflowError) as caught:
                    remote.raise_for_tool_error(error_payload(code))
                self.assertEqual(caught.exception.code, code)
                self.assertGreater(len(caught.exception.guidance), 30)
                self.assertFalse(any(marker in caught.exception.guidance for marker in sensitive))

    def test_unknown_or_malformed_remote_error_code_uses_fixed_local_error(self):
        sentinel = "Bearer SECRET https://signed.invalid/?token=SECRET /private/raw.csv\r\nX-Leak: yes"
        malformed = (sentinel, None, 17, [sentinel], {"code": sentinel})
        for code in malformed:
            with self.subTest(code_type=type(code).__name__):
                payload = error_payload("AUTH_MISSING", message=sentinel)
                payload["error"]["code"] = code
                with self.assertRaises(remote.WorkflowError) as caught:
                    remote.raise_for_tool_error(payload)
                self.assertEqual(caught.exception.code, "REMOTE_ERROR_INVALID")
                self.assertEqual(caught.exception.guidance, remote._ERROR_GUIDANCE["REMOTE_ERROR_INVALID"])
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("signed.invalid", str(caught.exception))
                self.assertNotIn("/private/raw.csv", str(caught.exception))

        for malformed_error in (None, sentinel, [sentinel], {}):
            with self.subTest(error_type=type(malformed_error).__name__):
                payload = {"contract_version": remote.CONTRACT_VERSION, "error": malformed_error}
                with self.assertRaises(remote.WorkflowError) as caught:
                    remote.raise_for_tool_error(payload)
                self.assertEqual(caught.exception.code, "REMOTE_ERROR_INVALID")
                self.assertNotIn("SECRET", str(caught.exception))

    def test_malicious_response_upload_headers_fail_closed_without_echo(self):
        files = remote.inspect_local_files({"google_ads_shopping": self.google})
        sentinels = (
            {"x-safe\r\nAuthorization-Bearer-SECRET": "ok"},
            {"x-safe": "Bearer SECRET\r\nX-Signed: https://signed.invalid/?token=SECRET /private/raw.csv"},
            {"x-safe": "non-ascii-credential-\u2603"},
        )
        for headers in sentinels:
            with self.subTest(headers=list(headers)):
                response = self.prepare_response(files)
                response["uploads"]["google_ads_shopping"]["required_headers"] = headers
                put_calls = []
                with self.assertRaises(remote.WorkflowError) as caught:
                    remote.upload_files(files, response, lambda *args: put_calls.append(args), now=NOW)
                self.assertEqual(caught.exception.code, "UPLOAD_HEADERS_INVALID")
                self.assertEqual(caught.exception.guidance, remote._ERROR_GUIDANCE["UPLOAD_HEADERS_INVALID"])
                self.assertEqual(put_calls, [])
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("signed.invalid", str(caught.exception))
                self.assertNotIn("/private/raw.csv", str(caught.exception))
                self.assertNotIn("\r", str(caught.exception))
                self.assertNotIn("\n", str(caught.exception))

    def test_stdlib_header_serialization_error_is_static_and_redacted(self):
        sentinel = "Bearer SECRET https://signed.invalid/?token=SECRET /private/raw.csv\r\nX-Leak: yes"

        class HeaderFailureConnection:
            def putrequest(self, *_args, **_kwargs):
                return None

            def putheader(self, *_args, **_kwargs):
                raise ValueError(sentinel)

            def close(self):
                return None

        with mock.patch.object(remote.ssl, "create_default_context", return_value=object()):
            with mock.patch.object(remote.http.client, "HTTPSConnection", return_value=HeaderFailureConnection()):
                with self.assertRaises(remote.WorkflowError) as caught:
                    remote.direct_https_put(
                        "https://upload.invalid/private/raw.csv?token=SECRET",
                        {"content-type": "text/csv"},
                        BytesIO(RAW_MARKER),
                        len(RAW_MARKER),
                    )
        self.assertEqual(caught.exception.code, "UPLOAD_HTTP_ERROR")
        self.assertEqual(caught.exception.guidance, remote._ERROR_GUIDANCE["UPLOAD_HTTP_ERROR"])
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertNotIn("upload.invalid", str(caught.exception))
        self.assertNotIn("/private/raw.csv", str(caught.exception))
        self.assertNotIn("\r", str(caught.exception))
        self.assertNotIn("\n", str(caught.exception))

    def test_hostile_external_urls_fail_closed_for_upload_and_artifacts(self):
        hostile_urls = (
            "https://upload\u2100BearerSECRET.invalid/path?token=SECRET",
            "https://[BearerSECRET.invalid/path?token=SECRET",
            "https://upload.invalid:BearerSECRET/path?token=SECRET",
            "https://BearerSECRET:tokenSECRET@upload.invalid/private/raw.csv",
        )
        files = remote.inspect_local_files({"google_ads_shopping": self.google})
        for hostile_url in hostile_urls:
            with self.subTest(stage="upload", url_kind=hostile_urls.index(hostile_url)):
                self.assertFalse(remote._valid_https_url(hostile_url))
                response = self.prepare_response(files)
                response["uploads"]["google_ads_shopping"]["put_url"] = hostile_url
                put_calls = []
                with self.assertRaises(remote.WorkflowError) as caught:
                    remote.upload_files(files, response, lambda *args: put_calls.append(args), now=NOW)
                self.assertEqual(caught.exception.code, "UPLOAD_URL_INVALID")
                self.assertEqual(caught.exception.guidance, remote._ERROR_GUIDANCE["UPLOAD_URL_INVALID"])
                self.assertEqual(put_calls, [])
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("upload.invalid", str(caught.exception))
                self.assertNotIn("/private/raw.csv", str(caught.exception))

            with self.subTest(stage="artifact", url_kind=hostile_urls.index(hostile_url)):
                response = copy.deepcopy(FIXTURE["generate_response"])
                response["artifacts"][0]["download_url"] = hostile_url
                with self.assertRaises(remote.WorkflowError) as caught:
                    remote.present_generate_response(response, now=NOW)
                self.assertEqual(caught.exception.code, "ARTIFACT_EXPIRY_INVALID")
                self.assertEqual(caught.exception.guidance, remote._ERROR_GUIDANCE["ARTIFACT_EXPIRY_INVALID"])
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("upload.invalid", str(caught.exception))
                self.assertNotIn("/private/raw.csv", str(caught.exception))

    def test_artifact_expiry_is_fail_closed_and_never_returns_links(self):
        response = copy.deepcopy(FIXTURE["generate_response"])
        response["artifacts"][0]["expires_at"] = "2026-08-09T17:00:00Z"
        with self.assertRaises(remote.WorkflowError) as caught:
            remote.present_generate_response(response, now=NOW)
        self.assertEqual(caught.exception.code, "ARTIFACT_EXPIRY_INVALID")
        self.assertNotIn("download.invalid", caught.exception.guidance)

        response = copy.deepcopy(FIXTURE["generate_response"])
        response["artifacts"][2]["expiry_seconds"] = 3599
        with self.assertRaisesRegex(remote.WorkflowError, "Do not present or download"):
            remote.present_generate_response(response, now=NOW)

    def test_assumptions_require_strict_band_order_and_safe_ranges(self):
        for changed in (
            {"band_exc": 0.05, "band_high": 0.05},
            {"fixed_costs": -1},
            {"cogs_pct": 101},
        ):
            candidate = {**ASSUMPTIONS, **changed}
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(remote.WorkflowError, "strictly descending"):
                    remote.validate_assumptions(candidate)

    def test_upload_expiry_stops_before_opening_body(self):
        files = remote.inspect_local_files({"google_ads_shopping": self.google})
        response = self.prepare_response(files)
        response["upload_expires_at"] = "2026-08-09T17:00:00Z"
        calls = []
        with self.assertRaisesRegex(remote.WorkflowError, "15-minute upload session expired"):
            remote.upload_files(files, response, lambda *args: calls.append(args), now=NOW)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
