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

    def test_pages_side_effects_are_main_only_without_job_environment(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("environment:\n      name: github-pages", workflow)
        self.assertNotIn("steps.deployment.outputs.page_url", workflow)

        main_only_steps = (
            "Restore public report history",
            "Build public report site",
            "Persist sanitized public history",
            "Configure GitHub Pages",
            "Upload report site",
            "Publish report site",
        )
        main_guard = "if: ${{ github.ref == 'refs/heads/main' }}"
        for step_name in main_only_steps:
            step = workflow.split(f"- name: {step_name}", maxsplit=1)[1]
            self.assertTrue(
                step.lstrip().startswith(main_guard),
                f"{step_name} must only execute from main",
            )

        audit_step = workflow.split("- name: Upload audit snapshot", maxsplit=1)[1]
        self.assertTrue(audit_step.lstrip().startswith("if: always()"))
        self.assertNotIn(main_guard, audit_step.split("- name:", maxsplit=1)[0])

    def test_failure_alert_does_not_reference_secrets_in_if_expression(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        alert = workflow.split("- name: Alert Feishu when the pipeline fails", maxsplit=1)[1]
        self.assertIn("if: ${{ failure() }}", alert)
        self.assertNotIn("if: ${{ failure() && secrets.", alert)
        self.assertIn('if [ -z "$FEISHU_WEBHOOK_URL" ]; then', alert)


if __name__ == "__main__":
    unittest.main()
