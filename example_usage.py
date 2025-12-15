#!/usr/bin/env python3
"""
Example usage of the Mobile QA Multi-Agent System

This script demonstrates how to run the test suite programmatically.
"""

import os
import sys
from mobileqa.main import main

if __name__ == "__main__":
    # Set your Gemini API key
    # os.environ["GEMINI_API_KEY"] = "your-api-key-here"

    # Example command-line arguments
    sys.argv = [
        "mobileqa",
        "--device", "emulator-5554",
        "--apk", "~/Downloads/Obsidian-1.4.16.apk",
        "--tests", "qa_tests.yaml",
        "--model", "gemini-2.0-flash-exp",
    ]

    # Run the main function
    main()
