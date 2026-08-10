"""Publish immutable, reviewable Aleph candidate artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import tempfile

from .schema import SCHEMA_VERSION
from .store import Store


class ExportError(RuntimeError):
    """Candidate records cannot form a coherent immutable export."""


def _bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def publish(store: Store, root: str) -> pathlib.Path:
    candidates = store.list("export_candidate")
    regression = sorted(
        (item for item in candidates if item["kind"] == "regression"),
        key=lambda item: item["candidate_id"])
    corpus = sorted(
        (item for item in candidates if item["kind"] == "corpus_proposal"),
        key=lambda item: item["candidate_id"])
    regression_bytes, corpus_bytes = _bytes(regression), _bytes(corpus)
    basis = {
        "schema_version": SCHEMA_VERSION,
        "regression_sha256": _sha(regression_bytes),
        "corpus_proposals_sha256": _sha(corpus_bytes),
        "candidate_ids": sorted(item["candidate_id"] for item in candidates),
    }
    export_id = hashlib.sha256(_bytes(basis)).hexdigest()[:20]
    manifest = {"export_id": export_id, **basis,
                "counts": {"regression": len(regression),
                           "corpus_proposals": len(corpus)}}
    files = {
        "regressions.json": regression_bytes,
        "corpus-proposals.json": corpus_bytes,
        "manifest.json": _bytes(manifest),
    }
    export_root = pathlib.Path(root).resolve() / "exports"
    export_root.mkdir(parents=True, exist_ok=True)
    destination = export_root / export_id
    if destination.exists():
        if all((destination / name).read_bytes() == data
               for name, data in files.items()):
            return destination
        raise ExportError("immutable export directory contains different bytes")
    temporary = pathlib.Path(tempfile.mkdtemp(prefix=".export-", dir=export_root))
    try:
        for name, data in files.items():
            path = temporary / name
            path.write_bytes(data)
            os.chmod(path, 0o444)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination
