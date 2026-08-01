import unittest

from jingcai.model_governance import AuditApproval, ExperimentManifest, validate_candidate_approval


def manifest() -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="wf-2026-08-01", model_id="universal-goals", model_version="0.2.0",
        created_at="2026-08-01T08:00:00+00:00", code_revision="abc123",
        dataset_manifest_sha256="a" * 64, validation_protocol="rolling-origin/v1",
        metrics={"log_loss_improvement": 0.01, "lockbox_matches": 300.0}, artifact_sha256="b" * 64,
    )


class ModelGovernanceTests(unittest.TestCase):
    def test_approved_requires_config_manifest_signed_audit_and_scope(self) -> None:
        evidence = manifest()
        approval = AuditApproval.issue(
            manifest=evidence, auditor_id="model-qa", signed_at="2026-08-01T09:00:00+00:00",
            decision="approved", scopes=[("UCL", "match_result")],
        )
        result = validate_candidate_approval(
            acceptance={"approved": True, "markets": {"match_result": True}}, manifest=evidence,
            approval=approval, competition_code="UCL", market="match_result",
        )
        self.assertTrue(result.approved)
        self.assertEqual(evidence.sha256, result.manifest_sha256)

    def test_manual_true_alone_is_rejected(self) -> None:
        result = validate_candidate_approval(
            acceptance={"approved": True, "markets": {"match_result": True}}, manifest=None,
            approval=None, competition_code="UCL", market="match_result",
        )
        self.assertFalse(result.approved)
        self.assertEqual("experiment_manifest_missing", result.reason)

    def test_tampered_approval_and_wrong_scope_are_rejected(self) -> None:
        evidence = manifest()
        approval = AuditApproval.issue(
            manifest=evidence, auditor_id="model-qa", signed_at="2026-08-01T09:00:00+00:00",
            decision="approved", scopes=[("UCL", "match_result")],
        )
        tampered = AuditApproval.from_record({**approval.to_record(), "decision": "rejected"})
        invalid = validate_candidate_approval(
            acceptance={"approved": True, "markets": {"match_result": True}}, manifest=evidence,
            approval=tampered, competition_code="UCL", market="match_result",
        )
        self.assertEqual("audit_signature_invalid", invalid.reason)
        wrong_scope = validate_candidate_approval(
            acceptance={"approved": True, "markets": {"match_result": True}}, manifest=evidence,
            approval=approval, competition_code="NTL", market="match_result",
        )
        self.assertEqual("audit_scope_missing", wrong_scope.reason)

    def test_records_reject_missing_fields_and_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing fields"):
            ExperimentManifest.from_record({})
        record = manifest().to_record()
        record["created_at"] = "2026-08-01T08:00:00"
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            ExperimentManifest.from_record(record)

