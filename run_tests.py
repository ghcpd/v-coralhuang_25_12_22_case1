#!/usr/bin/env python
"""
One-command test runner for API compatibility layer.
Runs all tests with clear PASS/FAIL output.
Exit code 0 on success, non-zero on failure.

Usage:
    python run_tests.py
"""

import sys
import unittest
from io import StringIO


def main():
    """Execute all tests and report results."""
    # Discover and run all tests in the current directory
    loader = unittest.TestLoader()
    suite = loader.discover(".", pattern="test_*.py")
    
    # Create a test runner with verbose output
    stream = StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)
    
    # Print output
    output = stream.getvalue()
    print(output)
    
    # Print summary
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("[PASS] ALL TESTS PASSED")
        print(f"  Ran {result.testsRun} tests")
        print("=" * 70)
        return 0
    else:
        print("[FAIL] TESTS FAILED")
        print(f"  Ran {result.testsRun} tests")
        print(f"  Failures: {len(result.failures)}")
        print(f"  Errors: {len(result.errors)}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
