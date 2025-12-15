"""
Supervisor Agent: Monitors test execution and determines PASS/FAIL verdict.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from ..llm.gemini_client import GeminiClient
from .executor import ExecutionResult


class VerdictType(Enum):
    """Test verdict types."""
    PASS = "PASS"
    FAIL_ACTION = "FAIL_ACTION"  # Failed to execute an action
    FAIL_ASSERTION = "FAIL_ASSERTION"  # Assertion failed
    RUNNING = "RUNNING"  # Still in progress


@dataclass
class TestVerdict:
    """Test execution verdict."""
    verdict: VerdictType
    reason: str
    step_number: int
    details: str = ""


class SupervisorAgent:
    """
    Supervisor agent that monitors test execution and provides verdicts.
    Distinguishes between failed actions and failed assertions.
    """

    def __init__(self, llm_client: GeminiClient, max_steps: int = 30):
        """
        Initialize Supervisor agent.

        Args:
            llm_client: Gemini client for LLM-based verification
            max_steps: Maximum steps before timeout
        """
        self.llm = llm_client
        self.max_steps = max_steps

    def evaluate_step(
        self,
        test_goal: str,
        step_number: int,
        action: Dict[str, Any],
        execution_result: ExecutionResult,
        screenshot_path: str,
        ui_xml_summary: str
    ) -> TestVerdict:
        """
        Evaluate a single test step.

        Args:
            test_goal: Test objective
            step_number: Current step number
            action: Action that was attempted
            execution_result: Result of action execution
            screenshot_path: Path to screenshot after action
            ui_xml_summary: UI state summary

        Returns:
            TestVerdict with verdict and reason
        """
        action_type = action.get("action_type")
        action_desc = action.get("description", "Unknown action")

        # Check if max steps exceeded
        if step_number >= self.max_steps:
            return TestVerdict(
                verdict=VerdictType.FAIL_ACTION,
                reason=f"Test exceeded maximum steps ({self.max_steps})",
                step_number=step_number,
                details="Test timeout - too many steps without completion"
            )

        # Handle action execution failure
        if not execution_result.success and action_type != "assert":
            return TestVerdict(
                verdict=VerdictType.FAIL_ACTION,
                reason=f"Failed to execute action: {action_desc}",
                step_number=step_number,
                details=execution_result.error or execution_result.message
            )

        # Handle "done" action - test completion
        if action_type == "done":
            return self._verify_final_state(
                test_goal=test_goal,
                step_number=step_number,
                screenshot_path=screenshot_path,
                ui_xml_summary=ui_xml_summary
            )

        # Handle assertion action
        if action_type == "assert":
            return self._verify_assertion(
                test_goal=test_goal,
                assertion=action.get("params", {}).get("condition", action_desc),
                step_number=step_number,
                screenshot_path=screenshot_path,
                ui_xml_summary=ui_xml_summary
            )

        # Regular action succeeded, continue
        return TestVerdict(
            verdict=VerdictType.RUNNING,
            reason=f"Step {step_number} completed: {action_desc}",
            step_number=step_number
        )

    def _verify_assertion(
        self,
        test_goal: str,
        assertion: str,
        step_number: int,
        screenshot_path: str,
        ui_xml_summary: str
    ) -> TestVerdict:
        """
        Verify an assertion using LLM.

        Args:
            test_goal: Test objective
            assertion: Assertion to verify
            step_number: Current step number
            screenshot_path: Path to screenshot
            ui_xml_summary: UI state summary

        Returns:
            TestVerdict indicating if assertion passed or failed
        """
        prompt = f"""You are verifying a test assertion for a mobile app.

TEST GOAL: {test_goal}

ASSERTION TO VERIFY: {assertion}

CURRENT UI STATE:
{ui_xml_summary}

Based on the screenshot and UI state, determine if the assertion is TRUE or FALSE.

Respond with JSON:
{{
    "assertion_holds": true/false,
    "explanation": "Brief explanation of why assertion is true or false"
}}"""

        try:
            result = self.llm.generate_json(
                prompt=prompt,
                image_path=screenshot_path,
                temperature=0.2
            )

            assertion_holds = result.get("assertion_holds", False)
            explanation = result.get("explanation", "No explanation provided")

            if assertion_holds:
                return TestVerdict(
                    verdict=VerdictType.RUNNING,
                    reason=f"Assertion passed: {assertion}",
                    step_number=step_number,
                    details=explanation
                )
            else:
                return TestVerdict(
                    verdict=VerdictType.FAIL_ASSERTION,
                    reason=f"Assertion failed: {assertion}",
                    step_number=step_number,
                    details=explanation
                )

        except Exception as e:
            return TestVerdict(
                verdict=VerdictType.FAIL_ASSERTION,
                reason=f"Failed to verify assertion: {assertion}",
                step_number=step_number,
                details=f"LLM verification error: {str(e)}"
            )

    def _verify_final_state(
        self,
        test_goal: str,
        step_number: int,
        screenshot_path: str,
        ui_xml_summary: str
    ) -> TestVerdict:
        """
        Verify final state when test is marked as done.

        Args:
            test_goal: Test objective
            step_number: Final step number
            screenshot_path: Path to final screenshot
            ui_xml_summary: Final UI state summary

        Returns:
            TestVerdict indicating PASS or FAIL_ASSERTION
        """
        prompt = f"""You are verifying the final state of a mobile app test.

TEST GOAL: {test_goal}

The test execution has been marked as complete. Analyze the current UI state to determine if the test goal was ACHIEVED.

CURRENT UI STATE:
{ui_xml_summary}

IMPORTANT VERIFICATION RULES:
1. For note creation with BOTH title AND body:
   - The title field MUST contain the specified title text (not "Untitled")
   - The body field MUST contain the specified body text
   - If EITHER title or body is missing/incorrect, the goal is NOT achieved

2. For vault creation:
   - Must be INSIDE the vault (seeing "Create new note" or vault content screen)
   - Not just having clicked the "Create" button

3. For settings/appearance verification:
   - Must have successfully navigated to the specified settings screen
   - Must verify the specific property mentioned in the goal

Based on the screenshot and UI state, determine if ALL requirements of the test goal are satisfied.

Respond with JSON:
{{
    "goal_achieved": true/false,
    "explanation": "Detailed explanation of why the goal was or was not achieved, including what was found vs what was expected"
}}"""

        try:
            result = self.llm.generate_json(
                prompt=prompt,
                image_path=screenshot_path,
                temperature=0.2
            )

            goal_achieved = result.get("goal_achieved", False)
            explanation = result.get("explanation", "No explanation provided")

            if goal_achieved:
                return TestVerdict(
                    verdict=VerdictType.PASS,
                    reason="Test goal achieved",
                    step_number=step_number,
                    details=explanation
                )
            else:
                return TestVerdict(
                    verdict=VerdictType.FAIL_ASSERTION,
                    reason="Test goal not achieved",
                    step_number=step_number,
                    details=explanation
                )

        except Exception as e:
            return TestVerdict(
                verdict=VerdictType.FAIL_ASSERTION,
                reason="Failed to verify final state",
                step_number=step_number,
                details=f"LLM verification error: {str(e)}"
            )

    def format_verdict(self, verdict: TestVerdict) -> str:
        """
        Format verdict for display.

        Args:
            verdict: TestVerdict to format

        Returns:
            Formatted verdict string
        """
        lines = [
            f"{'='*60}",
            f"TEST VERDICT: {verdict.verdict.value}",
            f"{'='*60}",
            f"Step: {verdict.step_number}",
            f"Reason: {verdict.reason}",
        ]

        if verdict.details:
            lines.append(f"Details: {verdict.details}")

        lines.append('='*60)

        return '\n'.join(lines)
