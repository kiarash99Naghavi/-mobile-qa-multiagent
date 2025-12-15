# Mobile QA Multi-Agent System

A multi-agent AI system for automated mobile app testing using natural language test definitions. This project implements a three-tier agent architecture (Supervisor-Planner-Executor) to enable autonomous QA testing on Android applications.

## Demo

[View demo video](demo.mp4)

## Overview

This system automates the execution of test cases written in plain English against Android applications. The implementation uses three specialized AI agents that collaborate to interpret test objectives, interact with the mobile UI, and accurately determine test outcomes.

**Agent Architecture:**

- **Planner Agent**: Analyzes current UI state through screenshots and XML hierarchy to determine the next appropriate action
- **Executor Agent**: Performs planned actions on the device via ADB commands
- **Supervisor Agent**: Monitors test execution and validates outcomes against expected results

A key design goal was enabling the system to differentiate between action failures (unable to locate UI elements) and assertion failures (elements found but state doesn't match expectations). This distinction provides more actionable test results.

## Key Features

- **Natural Language Test Definitions**: Write test cases in plain English using YAML format
- **Multimodal UI Understanding**: Combines screenshot analysis and UI XML hierarchy for robust state interpretation
- **Intelligent Dialog Handling**: Automatically detects and handles popups and permission dialogs
- **Granular Failure Classification**: Distinguishes between action failures (element not found) and assertion failures (incorrect state)
- **Comprehensive Artifact Generation**: Saves screenshots, UI dumps, and agent decisions at each execution step
- **Flexible LLM Backend**: Model-agnostic design with Google Gemini as the default provider
- **ADB Integration**: Direct Android device automation via Android Debug Bridge

## Requirements

- Python 3.9+
- Android SDK Platform-Tools (ADB)
- Android Emulator or physical device
- Google Gemini API key

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

### 2. Set Up Android Environment

Install ADB:
```bash
# macOS
brew install android-platform-tools

# Linux
sudo apt-get install android-tools-adb
```

Launch Android emulator:
```bash
# Use Android Studio AVD Manager or command line
emulator -avd Pixel_8 -no-snapshot-load -no-snapshot-save &
```

Verify connection:
```bash
adb devices
```

### 3. Configure API Key

```bash
export GEMINI_API_KEY="your-api-key-here"
```

### 4. Run Tests

```bash
python -m mobileqa.main \
  --device emulator-5554 \
  --apk path/to/app.apk \
  --tests qa_tests.yaml
```

## Usage

### Basic Usage

Run all tests:
```bash
python -m mobileqa.main \
  --device emulator-5554 \
  --apk ~/Downloads/Obsidian-1.4.16.apk \
  --tests qa_tests.yaml
```

Run a specific test:
```bash
python -m mobileqa.main \
  --device emulator-5554 \
  --tests qa_tests.yaml \
  --single-test test_create_note_pass
```

Use a different model:
```bash
python -m mobileqa.main \
  --device emulator-5554 \
  --tests qa_tests.yaml \
  --model gemini-2.0-flash-exp
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--device` | Android device ID | `emulator-5554` |
| `--apk` | Path to APK file to install | - |
| `--tests` | Path to tests YAML file | Required |
| `--model` | LLM model to use | `gemini-2.0-flash-exp` |
| `--artifacts` | Artifacts output directory | `artifacts` |
| `--reset-app` | Clear app data before each test | `false` |
| `--single-test` | Run only a specific test | - |

## Test Definition Format

Define tests in YAML format:

```yaml
tests:
  - name: test_create_note_pass
    package: md.obsidian
    goal: |
      Create a new note titled "Meeting Notes" and type "Daily Standup" into the body.
    setup:
      - "Launch Obsidian app"
      - "Ensure a vault exists"
    expected_result: PASS

  - name: test_invalid_element_fail
    package: md.obsidian
    goal: |
      Find and click the 'Print to PDF' button in the main file menu.
    expected_result: FAIL_ACTION
    reason: "This feature doesn't exist in mobile version"
```

### Test Result Types

- `PASS`: Test completed successfully
- `FAIL_ACTION`: Failed to execute an action (e.g., element not found)
- `FAIL_ASSERTION`: Test assertion failed (e.g., wrong color, missing text)

## Architecture

The system follows a linear pipeline where each agent has a specific responsibility in the test execution flow.

### Planner Agent

The Planner receives the test goal along with the current UI state (screenshot + XML hierarchy) and determines the next action to execute.

**Key Responsibilities:**
- Analyzes visible UI elements and their properties from the XML dump
- Selects appropriate actions based on the test objective and current screen state
- Identifies text input fields and determines when text entry is needed
- Outputs structured JSON action specifications for the Executor

### Executor Agent

The Executor takes planned actions and executes them on the Android device using ADB commands.

**Key Responsibilities:**
- Translates high-level actions into ADB commands
- Implements retry logic for flaky UI interactions
- Handles unexpected popups and permission dialogs automatically
- Manages text input with proper field focusing
- Captures post-action screenshots and UI dumps for verification

**Supported Action Types:**
- `tap_by_text` - Tap elements by visible text content
- `tap_xy` - Tap at specific screen coordinates
- `input_text` - Enter text into input fields
- `swipe` - Execute swipe gestures (up, down, left, right)
- `keyevent` - Send Android key events (back, home, enter, etc.)
- `assert` - Verify expected UI state or element properties
- `wait` - Pause execution for UI stabilization
- `done` - Signal successful test completion

### Supervisor Agent

The Supervisor monitors the entire test execution and makes the final pass/fail determination.

**Key Responsibilities:**
- Tracks test progress across all execution steps
- Uses LLM-based reasoning to verify assertion correctness
- Classifies failures as either action failures or assertion failures
- Validates final UI state against expected test outcomes
- Generates structured test result reports with detailed failure reasoning

## Artifacts

The system generates comprehensive debugging artifacts for each test execution step. All artifacts are saved to `artifacts/<test_name>/step_<N>/`:

| File | Description |
|------|-------------|
| `screenshot.png` | Screen capture before action execution |
| `screenshot_post.png` | Screen capture after action execution |
| `ui.xml` | Complete UI hierarchy dump (pre-action) |
| `ui_post.xml` | Complete UI hierarchy dump (post-action) |
| `ui_summary.txt` | Human-readable summary of visible UI elements |
| `action.json` | Planner's structured action decision |
| `execution_result.json` | Executor's execution result and any errors |
| `verdict.json` | Supervisor's step-level verdict and reasoning |

The final test summary (including overall pass/fail status and failure reasons) is saved to `artifacts/<test_name>/test_result.json`.

## Example Tests

I've included several test cases in `qa_tests.yaml` to demonstrate different scenarios:

1. **Create Vault** (Expected: PASS)
   Tests basic navigation and vault creation workflow

2. **Create Note** (Expected: PASS)
   Validates note creation with title and body text input

3. **Verify Appearance Icon Color** (Expected: FAIL_ASSERTION)
   Demonstrates assertion failure when UI element state doesn't match expectations

4. **Print to PDF** (Expected: FAIL_ACTION)
   Shows action failure when attempting to access a non-existent mobile feature

## Troubleshooting

### ADB not found
```bash
# Verify ADB is in PATH
which adb

# Add to PATH if needed (macOS/Linux)
export PATH="$PATH:~/Library/Android/sdk/platform-tools"
```

### Emulator not connecting
```bash
# Restart ADB server
adb kill-server
adb start-server
adb devices
```

### API key issues
```bash
# Verify API key is set
echo $GEMINI_API_KEY
```

## Extending the System

The architecture is designed to be extensible. Here are common extension points:

### Adding New Actions

To add custom action types, implement a handler method in [src/mobileqa/agents/executor.py](src/mobileqa/agents/executor.py):

```python
def _handle_custom_action(self, params, description):
    # Your implementation
    return ExecutionResult(success=True, message="Action completed")
```

### Using Different LLMs

The system is model-agnostic. To integrate a different LLM provider, create a new client in [src/mobileqa/llm/](src/mobileqa/llm/):

```python
class CustomLLMClient:
    def generate_json(self, prompt, image_path=None, **kwargs):
        # Your implementation
        return {"action_type": "...", ...}
```

## License

MIT License - see LICENSE file for details.
