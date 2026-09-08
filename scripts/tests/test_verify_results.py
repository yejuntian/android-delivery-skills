from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_results import VerificationError, _summarize, main


class VerifyResultsTests(unittest.TestCase):
    def test_all_skipped_tests_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TEST-all-skipped.xml"
            report.write_text(
                '<testsuite tests="3" failures="0" errors="0" skipped="3"/>',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(VerificationError, "所有测试均被跳过"):
                _summarize([report], latest_input=0)


class VerifiedHeadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        self.timestamp = 1_000_000_000
        self.git("init", "-q")
        self.spec = self.project / "document/task/docs/spec.md"
        self.spec.parent.mkdir(parents=True)
        self.spec.write_text("---\nstatus: confirmed\n---\n# Behavior\n", encoding="utf-8")
        (self.project / "Main.kt").write_text("fun value() = 1\n", encoding="utf-8")
        (self.project / ".gitignore").write_text("reports/\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "input")
        self.verified_head = self.git("rev-parse", "HEAD").strip()
        os.utime(self.spec, (self.timestamp, self.timestamp))
        self.report = self.project / "reports/TEST-behavior.xml"
        self.report.parent.mkdir()
        self.write_report('<testsuite tests="1" failures="0" errors="0" skipped="0"/>')

    def git(self, *args: str) -> str:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_AUTHOR_DATE=f"{self.timestamp} +0000",
            GIT_COMMITTER_DATE=f"{self.timestamp} +0000",
        )
        result = subprocess.run(
            [
                "git", "-c", "user.name=Skill Tests",
                "-c", "user.email=skill-tests@example.invalid",
                "-c", "core.hooksPath=" + os.devnull,
                "-c", "commit.gpgsign=false", *args,
            ],
            cwd=self.project,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def write_report(self, content: str) -> None:
        self.report.write_text(content, encoding="utf-8")
        os.utime(self.report, (self.timestamp + 10, self.timestamp + 10))

    def verify(self, expected: int, verified_head: str | None = None) -> str:
        arguments = [
            "--project", str(self.project), "--spec", str(self.spec),
            "--report", str(self.report),
        ]
        if verified_head is not None:
            arguments.extend(["--verified-head", verified_head])
        before = self.git("status", "--porcelain=v1"), self.git("rev-parse", "HEAD")
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = main(arguments)
        self.assertEqual(result, expected, output.getvalue())
        self.assertEqual(
            before, (self.git("status", "--porcelain=v1"), self.git("rev-parse", "HEAD"))
        )
        return output.getvalue()

    def test_unknown_verified_head_is_rejected(self) -> None:
        self.verify(2, "missing-commit")

    def test_unrelated_commit_is_rejected_even_with_the_same_tree(self) -> None:
        unrelated = self.git("commit-tree", "HEAD^{tree}", "-m", "unrelated root").strip()
        self.assertIn("祖先", self.verify(2, unrelated))

    def test_unchanged_spec_timestamp_does_not_invalidate_verified_content(self) -> None:
        os.utime(self.spec, (self.timestamp + 100, self.timestamp + 100))
        self.verify(0, self.verified_head)

    def test_changed_inputs_are_rejected_even_when_report_is_newer(self) -> None:
        for path in ["Main.kt", "document/task/api/api.md", "assets/payload.json", "README.md"]:
            with self.subTest(path=path):
                verified_head = self.git("rev-parse", "HEAD").strip()
                target = self.project / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("changed\n", encoding="utf-8")
                self.git("add", path)
                self.git("commit", "-qm", "changed input")
                self.assertIn("输入", self.verify(2, verified_head))

    def test_untracked_and_staged_inputs_are_rejected(self) -> None:
        target = self.project / "new dir/fixture.json"
        target.parent.mkdir()
        target.write_text("{}", encoding="utf-8")
        self.verify(2, self.verified_head)
        self.git("add", "new dir/fixture.json")
        self.verify(2, self.verified_head)

    def test_unstaged_deletion_is_rejected(self) -> None:
        (self.project / "Main.kt").unlink()
        self.verify(2, self.verified_head)

    def test_spec_change_cannot_be_treated_as_result_output(self) -> None:
        self.spec.write_text(
            "---\nstatus: confirmed\n---\n# Changed behavior\n", encoding="utf-8"
        )
        os.utime(self.spec, (self.timestamp - 1, self.timestamp - 1))
        self.verify(2, self.verified_head)

    def test_draft_spec_is_rejected(self) -> None:
        self.spec.write_text("---\nstatus: draft\n---\n", encoding="utf-8")
        self.assertIn("尚未确认", self.verify(2, self.verified_head))

    def test_old_and_failed_reports_remain_rejected(self) -> None:
        os.utime(self.report, (self.timestamp - 1, self.timestamp - 1))
        self.assertIn("早于", self.verify(2, self.verified_head))
        for content in [
            '<testsuite tests="0"/>',
            '<testsuite tests="1" skipped="1"/>',
            '<testsuite tests="1" failures="1"/>',
            '<testsuite tests="1" errors="1"/>',
        ]:
            with self.subTest(content=content):
                self.write_report(content)
                self.verify(2, self.verified_head)

    def test_result_only_commit_reuses_original_report(self) -> None:
        self.verify(0)
        result = self.spec.with_name("result.md")
        result.write_text("# Result\n", encoding="utf-8")
        self.verify(0, self.verified_head)
        self.timestamp += 20
        self.git("add", str(result.relative_to(self.project)))
        self.git("commit", "-qm", "result only")
        self.assertIn("早于", self.verify(2))
        self.verify(0, self.verified_head)

    def test_result_exclusion_does_not_cover_other_requirements(self) -> None:
        other_result = self.project / "document/other/docs/result.md"
        other_result.parent.mkdir(parents=True)
        other_result.write_text("# Other result\n", encoding="utf-8")
        self.verify(2, self.verified_head)

    def test_git_worktree_and_cli_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory) / "checkout"
            self.git("worktree", "add", "--detach", str(worktree), self.verified_head)
            result = subprocess.run(
                [
                    sys.executable, "-B",
                    str(Path(__file__).resolve().parents[1] / "verify_results.py"),
                    "--project", str(worktree),
                    "--spec", str(worktree / self.spec.relative_to(self.project)),
                    "--report", str(self.report), "--verified-head", self.verified_head,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("tests=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
