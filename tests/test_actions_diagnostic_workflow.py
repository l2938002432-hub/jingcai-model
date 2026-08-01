"""Static guardrails for the isolated GitHub Actions allocation diagnostic."""

from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "actions-diagnostic.yml"
)


class ActionsDiagnosticWorkflowTests(unittest.TestCase):
    def test_is_manual_only_and_read_only(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotIn("  push:\n", workflow)
        self.assertNotIn("  schedule:\n", workflow)
        self.assertIn("  contents: read\n", workflow)

    def test_does_not_use_secrets_or_delivery_steps(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("deploy-pages", workflow)
        self.assertNotIn("actions/deploy", workflow)
        self.assertIn("test \"$EVENT_NAME\" = \"workflow_dispatch\"", workflow)


if __name__ == "__main__":
    unittest.main()
