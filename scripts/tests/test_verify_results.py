from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_results import VerificationError, _summarize


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


if __name__ == "__main__":
    unittest.main()
