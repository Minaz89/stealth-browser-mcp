import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from response_handler import ResponseHandler
from stdio_guard import install_stdio_guard, is_guard_active, reset_stdio_guard_for_tests


class FakeStdout:
    def __init__(self):
        self.buffer = io.BytesIO(b"transport")
        self.written = []

    def write(self, data):
        self.written.append(data)
        return len(data)

    def flush(self):
        pass


class FakeStderr:
    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)
        return len(data)

    def flush(self):
        pass


class StdioGuardTests(unittest.TestCase):
    def test_stray_print_goes_to_stderr_and_transport_buffer_survives(self):
        real_stdout = sys.stdout
        real_stderr = sys.stderr
        fake_stdout = FakeStdout()
        fake_stderr = FakeStderr()
        sys.stdout = fake_stdout
        sys.stderr = fake_stderr
        try:
            self.assertTrue(install_stdio_guard())
            self.assertTrue(is_guard_active())
            self.assertFalse(install_stdio_guard())
            self.assertIs(sys.stdout.buffer, fake_stdout.buffer)
            print("dependency leak")
            self.assertEqual(fake_stdout.written, [])
            self.assertIn("dependency leak", "".join(fake_stderr.written))
        finally:
            reset_stdio_guard_for_tests(real_stdout)
            sys.stderr = real_stderr
        self.assertFalse(is_guard_active())

    def test_large_tool_result_spills_to_file_instead_of_inline(self):
        import tempfile

        with tempfile.TemporaryDirectory() as clone_dir:
            handler = ResponseHandler(max_tokens=1, clone_dir=clone_dir)
            result = handler.handle_response("x" * 1000, "script_result")
        self.assertIn("file_path", result)
        self.assertIn("reason", result)


if __name__ == "__main__":
    unittest.main()
