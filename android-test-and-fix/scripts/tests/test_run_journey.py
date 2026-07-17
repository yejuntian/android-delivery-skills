from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_journey.py"
SPEC = importlib.util.spec_from_file_location("run_journey", SCRIPT)
run_journey = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = run_journey
SPEC.loader.exec_module(run_journey)


class RunJourneyTest(unittest.TestCase):
    def make_harness(self, journey: str | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        directory = root / "harness-app" / "src" / "main" / "journeys"
        directory.mkdir(parents=True)
        if journey is not None:
            (directory / "sample.xml").write_text(journey, encoding="utf-8")
        return directory

    def test_rejects_zero_journeys(self):
        files, count, error = run_journey.validate_journeys(self.make_harness())
        self.assertEqual([], files)
        self.assertEqual(0, count)
        self.assertIn("0 个测试", error)

    def test_counts_actions_and_steps(self):
        harness = self.make_harness(
            "<journey><actions><action>Tap Home</action><step>Verify Home</step></actions></journey>"
        )
        files, count, error = run_journey.validate_journeys(harness)
        self.assertEqual(1, len(files))
        self.assertEqual(2, count)
        self.assertIsNone(error)

    def test_rejects_empty_journey(self):
        _, count, error = run_journey.validate_journeys(self.make_harness("<journey/>"))
        self.assertEqual(0, count)
        self.assertIn("不包含有效", error)

    def test_variant_task_suffix_preserves_camel_case(self):
        self.assertEqual("DemoDebug", run_journey.variant_task_suffix("demoDebug"))
        with self.assertRaises(ValueError):
            run_journey.variant_task_suffix("demo-debug")

    def test_environment_errors_never_trigger_app_repair(self):
        self.assertEqual(
            run_journey.HARNESS_FAILED,
            run_journey.classify_failure("Task ':harness-app:nope' not found"),
        )
        self.assertEqual(
            run_journey.APP_ASSERTION_FAILED,
            run_journey.classify_failure("Journey failed: assertion failed"),
        )
        self.assertEqual(
            run_journey.APP_ASSERTION_FAILED,
            run_journey.classify_failure("Gemini reasoning: assertion failed on Home screen"),
        )
        self.assertEqual(
            run_journey.HARNESS_FAILED,
            run_journey.classify_failure("Gradle test failed without an assertion signal"),
        )

    def test_reads_apk_from_output_metadata(self):
        root = Path(tempfile.mkdtemp())
        output = root / "app" / "build" / "outputs" / "apk" / "demo" / "debug"
        output.mkdir(parents=True)
        apk = output / "app-demo-debug.apk"
        apk.write_bytes(b"apk")
        (output / "output-metadata.json").write_text(
            json.dumps({"variantName": "demoDebug", "elements": [{"outputFile": apk.name}]}),
            encoding="utf-8",
        )
        self.assertEqual(apk, run_journey.find_apk_from_metadata(root, "app", "demoDebug"))

    def test_writes_json_and_markdown_reports(self):
        output = Path(tempfile.mkdtemp()) / "result.json"
        result = run_journey.JourneyResult(
            run_journey.PASS,
            "verified",
            0,
            device="device-1",
            journey_files=["home.xml"],
            action_count=2,
        )
        run_journey.write_result(result, output)
        self.assertEqual("PASS", json.loads(output.read_text(encoding="utf-8"))["status"])
        report = output.with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("Journey Harness 执行报告", report)
        self.assertIn("device-1", report)

    def test_resolves_cases_under_requirement_directory(self):
        config_path = Path(tempfile.mkdtemp()) / "local.yaml"
        config = {"workspace_root": str(config_path.parent), "requirement_dir": "requirement"}
        resolved = run_journey.resolve_journeys_dir(config_path, config, {}, None)
        expected = (config_path.parent / "requirement" / "test-cases" / "journeys").resolve()
        self.assertEqual(expected, resolved)

    def test_stages_only_current_journeys(self):
        source = Path(tempfile.mkdtemp())
        current = source / "current.xml"
        current.write_text("<journey><action>Verify current</action></journey>", encoding="utf-8")
        harness = Path(tempfile.mkdtemp())
        target = harness / "harness-app" / "src" / "main" / "journeys"
        target.mkdir(parents=True)
        (target / "stale.xml").write_text("<journey/>", encoding="utf-8")

        run_journey.stage_journeys([current], harness)

        self.assertFalse((target / "stale.xml").exists())
        self.assertEqual(current.read_text(encoding="utf-8"),
                         (target / "current.xml").read_text(encoding="utf-8"))

    def test_skips_journey_when_ui_is_not_applicable(self):
        no_ui = run_journey.skip_result("none")
        visual = run_journey.skip_result("visual")
        self.assertEqual(run_journey.SKIPPED_NO_UI, no_ui.status)
        self.assertEqual(run_journey.SKIPPED_VISUAL_ONLY, visual.status)
        self.assertEqual(0, no_ui.exit_code)
        self.assertEqual(0, visual.exit_code)
        self.assertIsNone(run_journey.skip_result("behavior"))


if __name__ == "__main__":
    unittest.main()
