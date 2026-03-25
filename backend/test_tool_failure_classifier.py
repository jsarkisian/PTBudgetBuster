"""Tests for tool_failure_classifier.py"""
import unittest
from tool_failure_classifier import FailureType, classify_failure


class TestClassifyFailureSyntaxErrors(unittest.TestCase):

    def test_flag_provided_but_not_defined(self):
        result = classify_failure("subfinder", "", "subfinder: flag provided but not defined: -timeout", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)
        self.assertIn("-timeout", result.lesson)

    def test_invalid_option(self):
        result = classify_failure("nmap", "", "nmap: invalid option -- 'x'", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)

    def test_unknown_flag(self):
        result = classify_failure("httpx", "", "unknown flag: --bad-flag", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)
        self.assertIn("--bad-flag", result.lesson)

    def test_unrecognized_in_output(self):
        result = classify_failure("nmap", "unrecognized option --foo", "", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)

    def test_command_not_found(self):
        result = classify_failure("notarealthing", "", "notarealthing: command not found", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)
        self.assertIn("command not found", result.lesson)

    def test_invalid_argument(self):
        result = classify_failure("nmap", "", "invalid argument: badvalue", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)
        self.assertIn("badvalue", result.lesson)

    def test_usage_colon_in_output(self):
        result = classify_failure("tool", "Usage: tool [options]", "", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)

    def test_no_such_option(self):
        result = classify_failure("tool", "", "no such option: --foo", "error")
        self.assertEqual(result.failure_type, FailureType.SYNTAX_ERROR)


class TestClassifyFailureAuthErrors(unittest.TestCase):

    def test_401_in_error(self):
        result = classify_failure("subfinder", "", "unexpected status code 401", "error")
        self.assertEqual(result.failure_type, FailureType.AUTH_ERROR)

    def test_403_in_output(self):
        result = classify_failure("httpx", "403 Forbidden", "", "error")
        self.assertEqual(result.failure_type, FailureType.AUTH_ERROR)

    def test_unauthorized(self):
        result = classify_failure("tool", "", "Unauthorized access", "error")
        self.assertEqual(result.failure_type, FailureType.AUTH_ERROR)

    def test_api_key_required(self):
        result = classify_failure("tool", "API key required", "", "error")
        self.assertEqual(result.failure_type, FailureType.AUTH_ERROR)

    def test_forbidden(self):
        result = classify_failure("tool", "", "403 forbidden response", "error")
        self.assertEqual(result.failure_type, FailureType.AUTH_ERROR)


class TestClassifyFailureNone(unittest.TestCase):

    def test_success(self):
        result = classify_failure("nmap", "80/tcp open http", "", "success")
        self.assertEqual(result.failure_type, FailureType.NONE)

    def test_no_results(self):
        result = classify_failure("subfinder", "", "", "success")
        self.assertEqual(result.failure_type, FailureType.NONE)

    def test_timeout(self):
        result = classify_failure("nmap", "", "connection timed out", "error")
        self.assertEqual(result.failure_type, FailureType.NONE)

    def test_generic_error(self):
        result = classify_failure("tool", "", "something went wrong", "error")
        self.assertEqual(result.failure_type, FailureType.NONE)


class TestLessonExtraction(unittest.TestCase):

    def test_extracts_flag_name(self):
        result = classify_failure("subfinder", "", "subfinder: flag provided but not defined: -timeout", "error")
        self.assertEqual(result.lesson, "flag '-timeout' is not supported")

    def test_extracts_invalid_option(self):
        result = classify_failure("nmap", "", "invalid option: --badopt", "error")
        self.assertIn("--badopt", result.lesson)

    def test_bash_lesson_prefix(self):
        result = classify_failure("bash", "", "subfinder: flag provided but not defined: -timeout", "error")
        self.assertTrue(result.lesson.startswith("bash error: "))

    def test_bash_lesson_truncated_at_100(self):
        long_error = "x" * 200
        result = classify_failure("bash", "", long_error, "error")
        # "bash error: " prefix (12 chars) + 100 chars of error = 112
        self.assertLessEqual(len(result.lesson), 115)

    def test_fallback_lesson_uses_error(self):
        result = classify_failure("nmap", "", "usage: nmap [options]", "error")
        self.assertGreater(len(result.lesson), 0)


if __name__ == "__main__":
    unittest.main()
