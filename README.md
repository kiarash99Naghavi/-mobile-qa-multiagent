# Mobile QA Multi-Agent System

An autonomous multi-agent system for mobile app testing using natural language test definitions. The system implements a Supervisor-Planner-Executor architecture to automate QA testing on Android applications.

## Overview

This system executes natural language test cases on Android applications using a three-agent architecture:

- **Planner Agent**: Analyzes UI state and determines next action
- **Executor Agent**: Executes planned actions on the device
- **Supervisor Agent**: Monitors execution and validates test outcomes

The agents work together to interpret test goals, navigate the app, and accurately report pass/fail results while distinguishing between action failures and assertion failures.

## Features

- Natural language test definitions in YAML format
- Screenshot + UI XML context for robust state understanding
- Automatic popup and dialog handling
- Distinguishes between action failures and assertion failures
- Artifact saving after each step (screenshots, UI dumps, verdicts)
- Swappable LLM models (default: Google Gemini)
- ADB-based Android device automation

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

### Planner Agent

Analyzes the current UI state (screenshot + XML hierarchy) and decides what action to take next based on the test goal.

**Capabilities:**
- Context-aware planning based on visible UI elements
- Automatic text input field detection
- Smart navigation decisions
- Returns structured JSON actions

### Executor Agent

Executes planned actions on the Android device via ADB commands.

**Capabilities:**
- Action execution with retry logic
- Automatic popup handling
- Text input with field focusing
- Screenshot capture and UI dumps
- Error recovery

**Supported Actions:**
- `tap_by_text` - Tap on visible text elements
- `tap_xy` - Tap at specific coordinates
- `input_text` - Type text into input fields
- `swipe` - Swipe gestures
- `keyevent` - Send key events
- `assert` - Verify UI state
- `wait` - Wait for UI changes
- `done` - Complete test successfully

### Supervisor Agent

Monitors test execution and evaluates outcomes.

**Capabilities:**
- Step-by-step execution monitoring
- LLM-based assertion verification
- Distinguishes between action failures and assertion failures
- Final state validation
- Comprehensive test reporting

## Artifacts

Each test run generates detailed artifacts in `artifacts/<test_name>/step_<N>/`:

- `screenshot.png` - Screenshot before action
- `screenshot_post.png` - Screenshot after action
- `ui.xml` - UI hierarchy dump
- `ui_post.xml` - UI hierarchy after action
- `ui_summary.txt` - Human-readable UI summary
- `action.json` - Planned action
- `execution_result.json` - Execution result
- `verdict.json` - Supervisor verdict

Test summary is saved to `artifacts/<test_name>/test_result.json`.

## Example Tests

The repository includes sample tests in `qa_tests.yaml`:

1. **Create Vault** (PASS) - Create and enter a new vault
2. **Create Note** (PASS) - Create a note with specific content
3. **Verify Appearance Icon Color** (FAIL_ASSERTION) - Assert icon color mismatch
4. **Print to PDF** (FAIL_ACTION) - Attempt to access non-existent feature

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

### Adding New Actions

Implement handler in `src/mobileqa/agents/executor.py`:

```python
def _handle_custom_action(self, params, description):
    # Your implementation
    return ExecutionResult(success=True, message="Action completed")
```

### Using Different LLMs

Create a new client in `src/mobileqa/llm/`:

```python
class CustomLLMClient:
    def generate_json(self, prompt, image_path=None, **kwargs):
        # Your implementation
        return {"action_type": "...", ...}
```

Update `main.py` to use your client.

## License

MIT License - see LICENSE file for details.
