"""Static safety checks for the cloud workflow trigger contract."""

from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily.yml"


class DailyWorkflowContractTests(unittest.TestCase):
    def test_daily_workflow_keeps_only_intended_entrypoints(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  schedule:\n", workflow)
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotIn("  push:\n", workflow)

    def test_daily_workflow_records_non_secret_execution_context(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Record safe run context", workflow)
        self.assertIn("EVENT_NAME: ${{ github.event_name }}", workflow)
        self.assertIn("HAS_RELAY_INPUT: ${{ inputs.snapshot_gzip_base64 != '' }}", workflow)

    def test_failure_alert_does_not_reference_secrets_in_if_expression(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        alert = workflow.split("- name: Alert Feishu when the pipeline fails", maxsplit=1)[1]
        self.assertIn("if: ${{ failure() }}", alert)
        self.assertNotIn("if: ${{ failure() && secrets.", alert)
        self.assertIn('if [ -z "$FEISHU_WEBHOOK_URL" ]; then', alert)


if __name__ == "__main__":
    unittest.main()
