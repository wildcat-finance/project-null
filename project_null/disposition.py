"""Apply fail-closed downstream acknowledgements to retained candidates."""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections import Counter
from dataclasses import dataclass

from .schema import (
    CandidateDisposition, CandidateResolution, stable_id, to_dict, utc_now,
)
from .store import Store, StoreError


class DispositionError(RuntimeError):
    """A downstream acknowledgement cannot be bound to Null's candidates."""


_REPORT_V1_KEYS = {"candidate_count", "cases", "counts", "export_id", "ready"}
_CASE_V1_KEYS = {
    "candidate_id", "expected", "golden_id", "issue", "question", "status",
}
_REPORT_V2_KEYS = _REPORT_V1_KEYS | {"evolution", "schema_version"}
_CASE_V2_KEYS = {
    "candidate_id", "expected", "golden_id", "kind", "question", "reference",
    "status",
}
_REPORT_V2_EVOLUTION = "mixed-candidate-dispositions-v2"
_COUNT_KEYS = {"accepted", "deferred", "duplicate", "needs_review", "rejected"}
_TERMINAL = {"accepted", "duplicate", "rejected"}
_ALEPH_ROUTES = {
    "clarify", "corpus", "corpus+live", "correct", "easter_egg", "live",
    "partial", "refuse", "refuse+point", "triage",
}


@dataclass(frozen=True)
class CandidateCounts:
    total: int
    resolved: int
    unresolved: int


@dataclass(frozen=True)
class ApplyReport:
    export_id: str
    report_id: str
    applied: int
    reused: int
    deferred: int
    needs_review: int
    counts: CandidateCounts


def _bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: pathlib.Path) -> tuple[bytes, object]:
    try:
        data = path.read_bytes()
        return data, json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise DispositionError(f"cannot read {path}: {error}") from error


def _mapping(value, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise DispositionError(
            f"{label} fields differ: expected {sorted(keys)}, got {actual}")
    return value


def _load_export(artifacts_path: str, export_id: str) -> tuple[dict, list[dict]]:
    root = pathlib.Path(artifacts_path).resolve() / "exports" / export_id
    manifest_bytes, manifest_value = _read_json(root / "manifest.json")
    regression_bytes, regression_value = _read_json(root / "regressions.json")
    corpus_bytes, corpus_value = _read_json(root / "corpus-proposals.json")
    manifest = _mapping(manifest_value, {
        "candidate_ids", "corpus_proposals_sha256", "counts", "export_id",
        "regression_sha256", "schema_version",
    }, "export manifest")
    if manifest_bytes != _bytes(manifest):
        raise DispositionError("export manifest is not canonical Null JSON")
    if manifest["schema_version"] != 1 or manifest["export_id"] != export_id:
        raise DispositionError("export manifest identity does not match report")
    if _sha256(regression_bytes) != manifest["regression_sha256"]:
        raise DispositionError("regressions.json hash does not match manifest")
    if _sha256(corpus_bytes) != manifest["corpus_proposals_sha256"]:
        raise DispositionError("corpus-proposals.json hash does not match manifest")
    if regression_bytes != _bytes(regression_value):
        raise DispositionError("regressions.json is not canonical Null JSON")
    if corpus_bytes != _bytes(corpus_value):
        raise DispositionError("corpus-proposals.json is not canonical Null JSON")
    if not isinstance(regression_value, list) or not isinstance(corpus_value, list):
        raise DispositionError("export candidate files must contain lists")
    if any(not isinstance(item, dict)
           for item in [*regression_value, *corpus_value]):
        raise DispositionError("export contains a malformed candidate")
    candidates = sorted(
        [*regression_value, *corpus_value], key=lambda item: item.get("candidate_id", ""))
    candidate_ids = []
    for item in candidates:
        if (not isinstance(item, dict)
                or not isinstance(item.get("candidate_id"), str)
                or item.get("record_type") != "export_candidate"
                or item.get("schema_version") != 1
                or item.get("kind") not in {"regression", "corpus_proposal"}
                or not isinstance(item.get("question"), str)):
            raise DispositionError("export contains a malformed candidate")
        candidate_ids.append(item["candidate_id"])
    if (candidate_ids != sorted(candidate_ids)
            or len(set(candidate_ids)) != len(candidate_ids)):
        raise DispositionError("export candidate IDs are not uniquely sorted")
    if manifest["candidate_ids"] != candidate_ids:
        raise DispositionError("manifest candidate IDs do not match export")
    if manifest["counts"] != {
            "regression": len(regression_value),
            "corpus_proposals": len(corpus_value)}:
        raise DispositionError("manifest counts do not match export")
    basis = {
        "schema_version": 1,
        "regression_sha256": manifest["regression_sha256"],
        "corpus_proposals_sha256": manifest["corpus_proposals_sha256"],
        "candidate_ids": candidate_ids,
    }
    if _sha256(_bytes(basis))[:20] != export_id:
        raise DispositionError("export ID is not derived from its manifest inputs")
    return manifest, candidates


def candidate_counts(store: Store) -> CandidateCounts:
    candidates = {item["candidate_id"] for item in store.list("export_candidate")}
    dispositions = store.list("candidate_disposition")
    resolved = {item["candidate_id"] for item in dispositions}
    if len(resolved) != len(dispositions):
        raise DispositionError("candidate has multiple terminal dispositions")
    unknown = sorted(resolved - candidates)
    if unknown:
        raise DispositionError(
            f"dispositions name unknown retained candidates: {unknown}")
    return CandidateCounts(
        total=len(candidates), resolved=len(resolved),
        unresolved=len(candidates - resolved))


def apply(store: Store, artifacts_path: str, report_path: str,
          acknowledged_at: str | None = None) -> ApplyReport:
    _, report_value = _read_json(pathlib.Path(report_path).resolve())
    if isinstance(report_value, dict) and "schema_version" in report_value:
        report = _mapping(report_value, _REPORT_V2_KEYS, "acknowledgement report")
        if (report["schema_version"] != 2
                or report["evolution"] != _REPORT_V2_EVOLUTION):
            raise DispositionError("unsupported acknowledgement evolution")
        report_version = 2
    else:
        report = _mapping(report_value, _REPORT_V1_KEYS, "acknowledgement report")
        report_version = 1
    export_id = report["export_id"]
    if not isinstance(export_id, str):
        raise DispositionError("report export_id must be a string")
    _, exported = _load_export(artifacts_path, export_id)
    exported_by_id = {item["candidate_id"]: item for item in exported}

    if (isinstance(report["candidate_count"], bool)
            or report["candidate_count"] != len(exported)):
        raise DispositionError("report candidate_count does not match export")
    counts = _mapping(report["counts"], _COUNT_KEYS, "report counts")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in counts.values()):
        raise DispositionError("report counts must be nonnegative integers")
    cases = report["cases"]
    if not isinstance(cases, list):
        raise DispositionError("report cases must be a list")
    statuses = Counter()
    seen = set()
    terminal = []
    for value in cases:
        case = _mapping(
            value, _CASE_V2_KEYS if report_version == 2 else _CASE_V1_KEYS,
            "report case")
        candidate_id = case["candidate_id"]
        status = case["status"]
        if not isinstance(candidate_id, str) or candidate_id in seen:
            raise DispositionError("report candidate IDs must be unique strings")
        if not isinstance(status, str) or status not in _COUNT_KEYS:
            raise DispositionError(f"unsupported disposition status {status!r}")
        if (not isinstance(case["expected"], str)
                or case["expected"] not in _ALEPH_ROUTES):
            raise DispositionError("report case has unsupported Aleph route")
        candidate = exported_by_id.get(candidate_id)
        if candidate is None:
            raise DispositionError(f"report names unknown candidate {candidate_id}")
        if case["question"] != candidate.get("question"):
            raise DispositionError(f"report changed question for {candidate_id}")
        candidate_kind = candidate["kind"]
        if report_version == 1:
            if candidate_kind != "regression":
                raise DispositionError(
                    "version 1 reports cannot disposition corpus proposals")
            reference_value = case["issue"]
        else:
            if case["kind"] != candidate_kind:
                raise DispositionError(
                    f"report changed candidate kind for {candidate_id}")
            reference_value = case["reference"]
        seen.add(candidate_id)
        statuses[status] += 1
        golden_id = case["golden_id"]
        if status in {"accepted", "duplicate"} and candidate_kind == "regression":
            if (not isinstance(golden_id, str) or not golden_id.strip()
                    or reference_value is not None):
                raise DispositionError(
                    f"{status} disposition needs only a golden case reference")
            reference = golden_id
        elif status in {"accepted", "duplicate"}:
            if (golden_id is not None or not isinstance(reference_value, str)
                    or not reference_value.strip()):
                raise DispositionError(
                    f"{status} corpus disposition needs only an evidence reference")
            reference = reference_value
        elif status == "rejected":
            if golden_id is not None:
                raise DispositionError("rejected disposition cannot name a golden case")
            reference = (reference_value if isinstance(reference_value, str)
                         and reference_value.strip() else "rejected")
        elif status == "deferred":
            if (golden_id is not None or not isinstance(reference_value, str)
                    or not reference_value.strip()):
                raise DispositionError(
                    "deferred disposition needs only a tracking reference")
            continue
        else:
            if golden_id is not None or reference_value is not None:
                raise DispositionError("needs_review disposition cannot name a target")
            continue
        terminal.append((candidate_id, status, reference))

    if seen != set(exported_by_id):
        raise DispositionError("report is partial or names the wrong candidate set")
    if counts != {name: statuses.get(name, 0) for name in _COUNT_KEYS}:
        raise DispositionError("report counts do not match cases")
    if report["ready"] is not (statuses.get("needs_review", 0) == 0):
        raise DispositionError("report ready flag does not match review state")

    report_id = _sha256(_bytes(report))
    timestamp = acknowledged_at or utc_now()
    new_records = []
    reused = 0
    for candidate_id, status, reference in terminal:
        record = CandidateDisposition(
            disposition_id=stable_id(
                "disposition", {"candidate_id": candidate_id}),
            candidate_id=candidate_id,
            export_id=export_id,
            resolution=CandidateResolution(status),
            reference=reference,
            report_id=report_id,
            acknowledged_at=timestamp,
        )
        existing = store.get(record.disposition_id)
        if existing is None:
            new_records.append(record)
            continue
        if (existing.get("candidate_id") != candidate_id
                or existing.get("resolution") != status
                or existing.get("reference") != reference):
            raise DispositionError(
                f"candidate {candidate_id} has a conflicting acknowledgement")
        reused += 1
    try:
        store.append_many(new_records)
    except StoreError as error:
        raise DispositionError("acknowledgements could not be committed") from error
    resulting = candidate_counts(store)
    return ApplyReport(
        export_id=export_id, report_id=report_id,
        applied=len(new_records), reused=reused,
        deferred=statuses.get("deferred", 0),
        needs_review=statuses.get("needs_review", 0),
        counts=resulting,
    )
