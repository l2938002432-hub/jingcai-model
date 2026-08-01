"""Versioned experiment evidence and fail-closed model approval checks.

This module intentionally does not change the legacy candidate pipeline yet.
Callers must opt in to :func:`validate_candidate_approval` before a manual
``approved: true`` setting can be replaced safely.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    """Return a stable hash for an evidence record."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExperimentManifest:
    """The minimum reproducible evidence produced by one model experiment."""

    experiment_id: str
    model_id: str
    model_version: str
    created_at: str
    code_revision: str
    dataset_manifest_sha256: str
    validation_protocol: str
    metrics: Mapping[str, float]
    artifact_sha256: str
    schema_version: int = SCHEMA_VERSION

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ExperimentManifest":
        required = {
            "experiment_id", "model_id", "model_version", "created_at", "code_revision",
            "dataset_manifest_sha256", "validation_protocol", "metrics", "artifact_sha256",
        }
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"experiment manifest missing fields: {', '.join(missing)}")
        if not isinstance(record["metrics"], Mapping):
            raise ValueError("experiment manifest metrics must be a mapping")
        _require_timestamp(str(record["created_at"]), "created_at")
        return cls(
            experiment_id=str(record["experiment_id"]),
            model_id=str(record["model_id"]),
            model_version=str(record["model_version"]),
            created_at=str(record["created_at"]),
            code_revision=str(record["code_revision"]),
            dataset_manifest_sha256=str(record["dataset_manifest_sha256"]),
            validation_protocol=str(record["validation_protocol"]),
            metrics={str(key): float(value) for key, value in record["metrics"].items()},
            artifact_sha256=str(record["artifact_sha256"]),
            schema_version=int(record.get("schema_version", SCHEMA_VERSION)),
        )

    @property
    def sha256(self) -> str:
        return _canonical_hash(self.to_record())


@dataclass(frozen=True)
class AuditApproval:
    """A scope-limited audit attestation for an immutable experiment manifest.

    ``signature`` is a tamper-evident deterministic record signature, not an
    identity-verifying cryptographic signature. Production use should replace
    it with a secret-backed or key-backed signer before untrusted writers can
    create approval records.
    """

    manifest_sha256: str
    auditor_id: str
    signed_at: str
    decision: str
    scopes: tuple[tuple[str, str], ...]
    signature: str
    schema_version: int = SCHEMA_VERSION

    def unsigned_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_sha256": self.manifest_sha256,
            "auditor_id": self.auditor_id,
            "signed_at": self.signed_at,
            "decision": self.decision,
            "scopes": [list(scope) for scope in self.scopes],
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.unsigned_record(), "signature": self.signature}

    @classmethod
    def issue(
        cls, *, manifest: ExperimentManifest, auditor_id: str, signed_at: str,
        decision: str, scopes: Sequence[tuple[str, str]],
    ) -> "AuditApproval":
        _require_timestamp(signed_at, "signed_at")
        normal_scopes = tuple(sorted((str(code), str(market)) for code, market in scopes))
        unsigned = {
            "schema_version": SCHEMA_VERSION,
            "manifest_sha256": manifest.sha256,
            "auditor_id": str(auditor_id),
            "signed_at": signed_at,
            "decision": str(decision),
            "scopes": [list(scope) for scope in normal_scopes],
        }
        return cls(signature=_canonical_hash(unsigned), scopes=normal_scopes, **{
            key: value for key, value in unsigned.items() if key != "scopes"
        })

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "AuditApproval":
        required = {"manifest_sha256", "auditor_id", "signed_at", "decision", "scopes", "signature"}
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"audit approval missing fields: {', '.join(missing)}")
        _require_timestamp(str(record["signed_at"]), "signed_at")
        scopes = record["scopes"]
        if not isinstance(scopes, Sequence) or isinstance(scopes, (str, bytes)):
            raise ValueError("audit approval scopes must be a sequence")
        normalized: list[tuple[str, str]] = []
        for scope in scopes:
            if not isinstance(scope, Sequence) or isinstance(scope, (str, bytes)) or len(scope) != 2:
                raise ValueError("each audit approval scope must be [competition_code, market]")
            normalized.append((str(scope[0]), str(scope[1])))
        return cls(
            manifest_sha256=str(record["manifest_sha256"]), auditor_id=str(record["auditor_id"]),
            signed_at=str(record["signed_at"]), decision=str(record["decision"]),
            scopes=tuple(sorted(normalized)), signature=str(record["signature"]),
            schema_version=int(record.get("schema_version", SCHEMA_VERSION)),
        )

    def signature_is_valid(self) -> bool:
        return self.signature == _canonical_hash(self.unsigned_record())


@dataclass(frozen=True)
class ApprovalCheck:
    approved: bool
    reason: str
    manifest_sha256: str | None = None


def validate_candidate_approval(
    *, acceptance: Mapping[str, Any], manifest: ExperimentManifest | None,
    approval: AuditApproval | None, competition_code: str, market: str,
) -> ApprovalCheck:
    """Fail closed unless config, reproducible evidence, and audit scope agree."""
    if acceptance.get("approved") is not True:
        return ApprovalCheck(False, "manual_acceptance_not_approved")
    markets = acceptance.get("markets")
    if not isinstance(markets, Mapping) or markets.get(market) is not True:
        return ApprovalCheck(False, "market_not_approved")
    if manifest is None:
        return ApprovalCheck(False, "experiment_manifest_missing")
    if approval is None:
        return ApprovalCheck(False, "audit_approval_missing", manifest.sha256)
    if not approval.signature_is_valid():
        return ApprovalCheck(False, "audit_signature_invalid", manifest.sha256)
    if approval.manifest_sha256 != manifest.sha256:
        return ApprovalCheck(False, "audit_manifest_mismatch", manifest.sha256)
    if approval.decision != "approved":
        return ApprovalCheck(False, "audit_not_approved", manifest.sha256)
    if (competition_code, market) not in approval.scopes:
        return ApprovalCheck(False, "audit_scope_missing", manifest.sha256)
    return ApprovalCheck(True, "approved_by_manifest_and_audit", manifest.sha256)


def _require_timestamp(value: str, field: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
