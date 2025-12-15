"""
Executor Agent: Executes planned actions on the mobile device.
"""
import time
from typing import Dict, Any, Tuple
from dataclasses import dataclass

from ..tools.adb import ADB
from ..tools.uixml import UIXMLParser


@dataclass
class ExecutionResult:
    """Result of action execution."""
    success: bool
    message: str
    error: str = ""


class ExecutorAgent:
    """
    Executor agent that executes actions on the mobile device.
    Handles retries, waits, and error recovery.
    """

    def __init__(self, adb: ADB, ui_parser: UIXMLParser, max_retries: int = 3):
        """
        Initialize Executor agent.

        Args:
            adb: ADB instance for device control
            ui_parser: UI XML parser for element location
            max_retries: Maximum retries for failed actions
        """
        self.adb = adb
        self.ui_parser = ui_parser
        self.max_retries = max_retries

    def execute_action(self, action: Dict[str, Any]) -> ExecutionResult:
        """
        Execute an action with retries.

        Args:
            action: Action dictionary from Planner

        Returns:
            ExecutionResult with success status and message
        """
        action_type = action.get("action_type")
        params = action.get("params", {})
        description = action.get("description", "Unknown action")

        # Backward compatibility: map old "tap" to appropriate handler
        if action_type == "tap":
            if "text" in params:
                action_type = "tap_by_text"
            elif "x" in params and "y" in params:
                action_type = "tap_xy"
            else:
                return ExecutionResult(
                    success=False,
                    message="Deprecated 'tap' action without valid params. Use 'tap_by_text' or 'tap_xy'.",
                    error="tap action requires either 'text' or 'x'/'y' params"
                )

        # Map action types to handler methods
        handlers = {
            "tap_by_text": self._handle_tap_by_text,
            "tap_xy": self._handle_tap_xy,
            "input_text": self._handle_input_text,
            "swipe": self._handle_swipe,
            "keyevent": self._handle_keyevent,
            "wait": self._handle_wait,
            "assert": self._handle_assert,
            "fail": self._handle_fail,
            "done": self._handle_done,
        }

        handler = handlers.get(action_type)
        if not handler:
            return ExecutionResult(
                success=False,
                message=f"Unknown action type: {action_type}",
                error=f"No handler for action type '{action_type}'"
            )

        # Execute with retries (except for assert, fail, and done)
        if action_type in ["assert", "done", "wait", "fail"]:
            return handler(params, description)

        # Retry logic for interactive actions
        for attempt in range(self.max_retries):
            result = handler(params, description)
            if result.success:
                return result

        return ExecutionResult(
            success=False,
            message=f"Failed after {self.max_retries} attempts: {description}",
            error=result.error
        )

    def _handle_tap_by_text(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """Handle tap_by_text action by finding element by text and tapping it."""
        text = params.get("text")
        if not text:
            return ExecutionResult(
                success=False,
                message="tap_by_text action missing 'text' parameter",
                error="No text specified for tap_by_text"
            )

        try:
            # Try exact match first
            success = self.ui_parser.tap_by_text(text, exact=True)
            if success:
                return ExecutionResult(
                    success=True,
                    message=f"Tapped element with text: {text}"
                )

            # Try substring match
            success = self.ui_parser.tap_by_text(text, exact=False)
            if success:
                return ExecutionResult(
                    success=True,
                    message=f"Tapped element containing text: {text}"
                )

            return ExecutionResult(
                success=False,
                message=f"Element not found: {text}",
                error=f"No UI element found with text '{text}'"
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Tap failed: {str(e)}",
                error=str(e)
            )

    def _handle_tap_xy(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """Handle tap at specific coordinates."""
        x = params.get("x")
        y = params.get("y")

        if x is None or y is None:
            return ExecutionResult(
                success=False,
                message="tap_xy action missing 'x' or 'y' parameter",
                error="Coordinates not specified"
            )

        try:
            self.adb.tap_xy(int(x), int(y))
            return ExecutionResult(
                success=True,
                message=f"Tapped at ({x}, {y})"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Tap failed at ({x}, {y}): {str(e)}",
                error=str(e)
            )

    def _handle_input_text(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """
        Handle text input by finding EditText field, focusing, clearing, and typing.
        """
        text = params.get("text")
        if not text:
            return ExecutionResult(
                success=False,
                message="input_text action missing 'text' parameter",
                error="No text specified for input"
            )

        try:
            # Dump UI to find EditText fields
            xml_path = self.ui_parser.dump_ui()
            nodes = self.ui_parser.parse_xml(xml_path)

            # Find EditText nodes
            edit_texts = [
                node for node in nodes
                if 'EditText' in node.class_name and node.enabled
            ]

            if not edit_texts:
                return ExecutionResult(
                    success=False,
                    message="No EditText field found on screen",
                    error="Cannot type text without an input field"
                )

            # Choose the best EditText based on field_type or defaults
            field_type = params.get("field_type", "").lower()
            
            # Sort by Y coordinate (top to bottom)
            sorted_by_y = sorted(edit_texts, key=lambda n: n.bounds[1])
            
            if field_type == "title":
                # Title often contains "Untitled" for new notes
                untitled = [et for et in edit_texts if "untitled" in (et.text or "").lower()]
                if untitled:
                    target = untitled[0]
                    print(f"  Selecting Title field (matches 'Untitled') at {target.center}")
                else:
                    # Fallback: Title is usually the topmost field
                    target = sorted_by_y[0]
                    print(f"  Selecting Title field (topmost) at {target.center}")
            
            elif field_type == "body":
                # Body is usually the largest field or the second one
                if len(edit_texts) > 1:
                    # Try to find the largest field by area
                    target = max(edit_texts, key=lambda n: (n.bounds[2] - n.bounds[0]) * (n.bounds[3] - n.bounds[1]))
                    # If largest is seemingly the same as title (e.g. title is short/small), ensure we don't pick title
                    # If title was "Untitled", avoid it
                    untitled_centers = [et.center for et in edit_texts if "untitled" in (et.text or "").lower()]
                    if target.center in untitled_centers and len(edit_texts) >= 2:
                        # Pick the other large one
                        target = sorted_by_y[1]
                    
                    # If target is simply the topmost one, check if there's a second one
                    elif target == sorted_by_y[0] and len(edit_texts) >= 2:
                        target = sorted_by_y[1]
                        
                    print(f"  Selecting Body field at {target.center}")
                else:
                    target = edit_texts[0]
            
            else:
                # Default behavior: focused > topmost
                focused = [et for et in edit_texts if et.focused]
                if focused:
                    target = focused[0]
                elif len(edit_texts) > 1:
                    # Multiple fields: prefer topmost (usually title field)
                    target = sorted_by_y[0]
                else:
                    # Single field: use it
                    target = edit_texts[0]

            # Tap to focus the EditText
            x, y = target.center
            self.adb.tap_xy(x, y, wait_after=0.0)

            # Clear existing text using select all + delete (more reliable)
            # Try Ctrl+A (Android 13+)
            try:
                self.adb._run_command(['shell', 'input', 'keycombination', '113', '29'])  # Ctrl+A
                self.adb.keyevent(67, wait_after=0.0)
            except:
                # Fallback: move to end and backspace multiple times
                self.adb.keyevent(123, wait_after=0.0)
                for _ in range(50):
                    self.adb.keyevent(67, wait_after=0.0)

            # Type the new text
            self.adb.type_text(text, wait_after=0.0)

            # CRITICAL FIX: If typing into title field, press ENTER to move to body
            # This allows the next input_text with field_type="body" to work correctly
            if field_type == "title":
                print(f"  Pressing ENTER after typing title to move to body field")
                self.adb.keyevent(66, wait_after=0.0)

            return ExecutionResult(
                success=True,
                message=f"Typed text into {field_type if field_type else 'EditText'}: {text}"
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Text input failed: {str(e)}",
                error=str(e)
            )

    def _handle_swipe(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """Handle swipe gesture."""
        direction = params.get("direction", "up").lower()

        try:
            # Get screen size
            width, height = self.adb.wm_size()

            # Define swipe coordinates based on direction
            swipes = {
                "up": (width // 2, height * 3 // 4, width // 2, height // 4),
                "down": (width // 2, height // 4, width // 2, height * 3 // 4),
                "left": (width * 3 // 4, height // 2, width // 4, height // 2),
                "right": (width // 4, height // 2, width * 3 // 4, height // 2),
            }

            if direction not in swipes:
                return ExecutionResult(
                    success=False,
                    message=f"Invalid swipe direction: {direction}",
                    error=f"Direction must be one of: {list(swipes.keys())}"
                )

            x1, y1, x2, y2 = swipes[direction]
            self.adb.swipe(x1, y1, x2, y2)
            return ExecutionResult(
                success=True,
                message=f"Swiped {direction}"
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Swipe failed: {str(e)}",
                error=str(e)
            )

    def _handle_keyevent(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """Handle key event."""
        key = params.get("key", "").upper()

        # Map key names to Android keycodes
        key_codes = {
            "BACK": 4,
            "HOME": 3,
            "ENTER": 66,
            "DEL": 67,
            "DELETE": 67,
            "TAB": 61,
            "SPACE": 62,
        }

        try:
            keycode = key_codes.get(key)
            if keycode is None:
                # Try to use as numeric keycode
                try:
                    keycode = int(key)
                except ValueError:
                    return ExecutionResult(
                        success=False,
                        message=f"Unknown key: {key}",
                        error=f"Key '{key}' not recognized"
                    )

            self.adb.keyevent(keycode)
            return ExecutionResult(
                success=True,
                message=f"Pressed key: {key}"
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Keyevent failed: {str(e)}",
                error=str(e)
            )

    def _handle_wait(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """Handle wait action (NO-OP in fast mode)."""
        seconds = params.get("seconds", 0.0)

        try:
            # NO SLEEP - instant return for maximum speed
            return ExecutionResult(
                success=True,
                message=f"Wait action skipped (fast mode, no delay)"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Wait failed: {str(e)}",
                error=str(e)
            )

    def _handle_assert(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """
        Handle assertion - check if condition is met.
        Note: Actual verification happens in Supervisor, this just records it.
        """
        condition = params.get("condition", description)

        return ExecutionResult(
            success=True,
            message=f"Assertion recorded: {condition}"
        )

    def _handle_fail(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """Handle fail action - explicit failure signal."""
        reason = params.get("reason", description)
        return ExecutionResult(
            success=False,
            message=f"Action failed explicitly: {reason}",
            error=reason
        )

    def _handle_done(self, params: Dict[str, Any], description: str) -> ExecutionResult:
        """Handle done action - test completion signal."""
        return ExecutionResult(
            success=True,
            message="Test marked as done"
        )
