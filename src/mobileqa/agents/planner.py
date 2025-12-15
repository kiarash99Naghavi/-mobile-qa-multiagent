"""
Planner Agent: Determines next action based on current state and test goal.
"""
from typing import Dict, Any, Optional
from pathlib import Path

from ..llm.gemini_client import GeminiClient


class PlannerAgent:
    """
    Planner agent that analyzes current UI state and determines next action.
    Returns structured JSON action for the Executor.
    """

    def __init__(self, llm_client: GeminiClient):
        """
        Initialize Planner agent.

        Args:
            llm_client: Gemini client for LLM inference
        """
        self.llm = llm_client

    def plan_next_action(
        self,
        test_goal: str,
        current_step: int,
        screenshot_path: str,
        ui_xml_summary: str,
        previous_actions: list = None
    ) -> Dict[str, Any]:
        """
        Plan the next action to achieve the test goal.

        Args:
            test_goal: Natural language description of test objective
            current_step: Current step number
            screenshot_path: Path to current screenshot
            ui_xml_summary: Summary of UI hierarchy
            previous_actions: List of previous actions taken

        Returns:
            Action dictionary with:
            {
                "action_type": "tap" | "swipe" | "input_text" | "assert" | "wait" | "done",
                "description": "Human-readable description",
                "params": {...}  # Action-specific parameters
            }
        """
        if previous_actions is None:
            previous_actions = []

        # Build context of previous actions with success/failure info
        if previous_actions:
            prev_actions_list = []
            for i, action in enumerate(previous_actions):
                desc = action.get('description', action.get('action_type'))
                action_type = action.get('action_type', 'unknown')
                # Include the action for context
                prev_actions_list.append(f"{i+1}. {action_type}: {desc}")
            prev_actions_str = "\n".join(prev_actions_list)
        else:
            prev_actions_str = "None - this is the first step"

        prompt = f"""You are a QA automation planner for mobile apps. Your task is to output EXACTLY ONE valid action in strict JSON format.

TEST GOAL:
{test_goal}

CURRENT STEP: {current_step}

PREVIOUS ACTIONS TAKEN:
{prev_actions_str}

CURRENT UI STATE (from XML hierarchy):
{ui_xml_summary}

Based on the screenshot and UI state, determine the NEXT action to take.

STRICT ACTION SCHEMA - You MUST output valid JSON matching ONE of these:

1. tap_by_text - Tap on a visible text element
   {{"action_type": "tap_by_text", "description": "...", "params": {{"text": "exact visible text"}}}}
   REQUIREMENTS:
   - params.text MUST be a non-empty string that appears in the UI STATE above
   - DO NOT use tap_by_text if the text is not visible

2. tap_xy - Tap at specific pixel coordinates
   {{"action_type": "tap_xy", "description": "...", "params": {{"x": 540, "y": 1000}}}}
   REQUIREMENTS:
   - params.x and params.y MUST be integers
   - Use only when tap_by_text is not possible

3. input_text - Type text (automatically finds and focuses the best EditText field)
   {{"action_type": "input_text", "description": "...", "params": {{"text": "text to type", "field_type": "title"}}}}
   REQUIREMENTS:
   - Use this to type into input fields (vault name, note title, note content, etc.)
   - Executor will find the EditText, focus it, clear existing text, and type
   - params.text can be any string (even empty)
   - params.field_type is REQUIRED when creating notes with separate title and body:
     * Use "title" for the note title/heading (typically labeled "Untitled" initially)
     * Use "body" for the main content area (typically below the title)
     * When typing title, the system will automatically press ENTER to move to body field
   - DO NOT tap on input fields - use input_text instead.
   - For single-field inputs (like vault names), field_type can be omitted.

4. swipe - Swipe gesture
   {{"action_type": "swipe", "description": "...", "params": {{"direction": "up"}}}}
   REQUIREMENTS:
   - params.direction must be one of: "up", "down", "left", "right"

5. keyevent - Press a key
   {{"action_type": "keyevent", "description": "...", "params": {{"key": "BACK"}}}}
   REQUIREMENTS:
   - params.key must be one of: "BACK", "HOME", "ENTER", "DEL"

6. wait - Wait for UI to settle
   {{"action_type": "wait", "description": "...", "params": {{"seconds": 1.0}}}}

7. assert - Make an assertion about current state
   {{"action_type": "assert", "description": "...", "params": {{"condition": "text 'X' is visible"}}}}
   REQUIREMENTS:
   - Use this when the test goal requires VERIFYING a condition (e.g., icon is red, button exists)
   - Assertion failures result in FAIL_ASSERTION verdict
   - Examples: "Appearance icon is red", "Settings page visible", "Text 'Welcome' exists"

8. fail - Explicitly fail the test (e.g. feature not found)
   {{"action_type": "fail", "description": "Feature X not found", "params": {{"reason": "Menu option missing"}}}}
   REQUIREMENTS:
   - Use this when a required element is definitely missing after searching.
   - This signals FAIL_ACTION verdict.

9. done - Test complete
   {{"action_type": "done", "description": "Test goal achieved", "params": {{}}}}

CRITICAL RULES:
- NEVER output action_type "tap" - it is INVALID. Use "tap_by_text" or "tap_xy" or "input_text"
- For tap_by_text: params.text MUST be non-empty and visible in UI STATE
- For tap_xy: params.x and params.y MUST be present and numeric
- For input_text creating notes with title and body:
  * FIRST action: {{"action_type": "input_text", "params": {{"text": "Title Text", "field_type": "title"}}}}
  * SECOND action: {{"action_type": "input_text", "params": {{"text": "Body Text", "field_type": "body"}}}}
  * Do NOT use keyevent or tap between title and body - the system auto-handles navigation
- If you want to focus/click an input field to type, use "input_text" directly (do NOT tap first)
- When multiple input fields exist, specify "field_type" to disambiguate.
- DO NOT repeat the same action type if you just did it in the previous step - check PREVIOUS ACTIONS
- If you just used input_text successfully, move to the NEXT step (like typing body or tapping confirmation button)
- Check the CURRENT UI STATE carefully - it may have changed since the last action
- IMPORTANT: Common popups like "Allow", "USE THIS FOLDER", "OK" are auto-handled by the system
  * If you don't see these popups in the UI STATE, they were already handled
  * Check if the UI has already progressed past the popup stage
  * Example: If creating a vault and you see "Create new note" in UI STATE, the vault is already created
- When the test goal is achieved, return "done":
  * Vault created: ONLY if you are INSIDE the vault (see 'Create new note' or similar), not just after clicking create.
  * Note created: ONLY if you typed BOTH title AND body text as specified in the test goal
  * Settings opened: if UI shows Settings screen with options
- For navigating to Settings:
  * Look for gear icon (Settings)
  * Tap the gear icon to enter Settings
  * Once in Settings, navigate to specific sections (Appearance, General, etc.)
- For searching in menus (e.g. looking for 'Print to PDF'):
  * First tap to open menu (e.g., 3-dot menu or 'More options')
  * Search thoroughly through all visible menu items
  * If not found after thorough search, THEN return "fail"
  * Do NOT give up too quickly - check all visible items carefully
- If a required element is missing after THOROUGH search, return "fail" with reason
- For Settings/Appearance navigation: persist through multiple steps, don't fail early
- Return ONLY ONE action
- If stuck or goal clearly achieved, return "done" with explanation
- If goal is IMPOSSIBLE (missing feature after thorough search), return "fail"

Respond with valid JSON only:"""

        try:
            action = self.llm.generate_json(
                prompt=prompt,
                image_path=screenshot_path,
                temperature=0.3  # Lower temperature for more consistent planning
            )

            # Validate action structure
            required_fields = ["action_type", "description", "params"]
            for field in required_fields:
                if field not in action:
                    action[field] = {} if field == "params" else "unknown"

            return action

        except Exception as e:
            # Fallback: return done action on error
            return {
                "action_type": "done",
                "description": f"Planning failed: {str(e)}",
                "params": {}
            }

    def validate_action_schema(self, action: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate action schema strictly.

        Args:
            action: Action dictionary

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(action, dict):
            return False, "Action is not a dictionary"

        # Check required fields
        required_fields = ["action_type", "description", "params"]
        for field in required_fields:
            if field not in action:
                return False, f"Missing required field: {field}"

        action_type = action.get("action_type")
        params = action.get("params", {})

        # Valid action types (NOTE: "tap" is NOT valid)
        valid_action_types = [
            "tap_by_text", "tap_xy", "input_text", "swipe",
            "keyevent", "wait", "assert", "fail", "done"
        ]

        if action_type not in valid_action_types:
            return False, f"Invalid action_type '{action_type}'. Use one of: {', '.join(valid_action_types)}"

        # Validate params based on action type
        if action_type == "tap_by_text":
            if "text" not in params:
                return False, "tap_by_text requires params.text"
            if not params["text"] or not isinstance(params["text"], str):
                return False, "tap_by_text params.text must be a non-empty string"

        elif action_type == "tap_xy":
            if "x" not in params or "y" not in params:
                return False, "tap_xy requires params.x and params.y"
            if not isinstance(params["x"], (int, float)) or not isinstance(params["y"], (int, float)):
                return False, "tap_xy params.x and params.y must be numeric"

        elif action_type == "input_text":
            if "text" not in params:
                return False, "input_text requires params.text"
            if not isinstance(params["text"], str):
                return False, "input_text params.text must be a string"

        elif action_type == "swipe":
            if "direction" not in params:
                return False, "swipe requires params.direction"
            if params["direction"] not in ["up", "down", "left", "right"]:
                return False, "swipe params.direction must be one of: up, down, left, right"

        elif action_type == "keyevent":
            if "key" not in params:
                return False, "keyevent requires params.key"

        return True, ""

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """
        Validate action structure (deprecated - use validate_action_schema).

        Args:
            action: Action dictionary

        Returns:
            True if valid, False otherwise
        """
        is_valid, _ = self.validate_action_schema(action)
        return is_valid
