"""
Supervisor Agent: Monitors test execution and determines PASS/FAIL verdict.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from ..llm.gemini_client import GeminiClient
from .executor import ExecutionResult
from ..evaluation.subgoals import (
    SubgoalDecomposition,
    SubgoalStatus,
    RewardCalculator,
    StepReward
)


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
    # NEW: Subgoal and reward tracking
    subgoals_achieved_this_step: List[str] = field(default_factory=list)
    step_reward: Optional[StepReward] = None


class SupervisorAgent:
    """
    Supervisor agent that monitors test execution and provides verdicts.
    Distinguishes between failed actions and failed assertions.
    """

    def __init__(
        self,
        llm_client: GeminiClient,
        max_steps: int = 30,
        subgoal_decomposition: Optional[SubgoalDecomposition] = None,
        reward_calculator: Optional[RewardCalculator] = None
    ):
        """
        Initialize Supervisor agent.

        Args:
            llm_client: Gemini client for LLM-based verification
            max_steps: Maximum steps before timeout
            subgoal_decomposition: Optional subgoal decomposition for tracking
            reward_calculator: Optional reward calculator for scoring
        """
        self.llm = llm_client
        self.max_steps = max_steps
        self.subgoal_decomposition = subgoal_decomposition
        self.reward_calculator = reward_calculator

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
            # Even on failure, check for subgoals (partial progress)
            subgoals_achieved = []
            step_reward = None
            if self.subgoal_decomposition and self.reward_calculator:
                subgoals_achieved = self.detect_subgoals_achieved(
                    step_number=step_number,
                    action=action,
                    execution_result=execution_result,
                    screenshot_path=screenshot_path,
                    ui_xml_summary=ui_xml_summary
                )
                step_reward = self.reward_calculator.calculate_step_reward(
                    step_number=step_number,
                    subgoals_achieved_this_step=subgoals_achieved
                )
            return TestVerdict(
                verdict=VerdictType.FAIL_ACTION,
                reason=f"Failed to execute action: {action_desc}",
                step_number=step_number,
                details=execution_result.error or execution_result.message,
                subgoals_achieved_this_step=subgoals_achieved,
                step_reward=step_reward
            )

        # Handle "done" action - test completion
        if action_type == "done":
            verdict = self._verify_final_state(
                test_goal=test_goal,
                step_number=step_number,
                screenshot_path=screenshot_path,
                ui_xml_summary=ui_xml_summary
            )
            # Add subgoal detection for final state
            subgoals_achieved = []
            step_reward = None
            if self.subgoal_decomposition and self.reward_calculator:
                subgoals_achieved = self.detect_subgoals_achieved(
                    step_number=step_number,
                    action=action,
                    execution_result=execution_result,
                    screenshot_path=screenshot_path,
                    ui_xml_summary=ui_xml_summary
                )
                step_reward = self.reward_calculator.calculate_step_reward(
                    step_number=step_number,
                    subgoals_achieved_this_step=subgoals_achieved
                )
            verdict.subgoals_achieved_this_step = subgoals_achieved
            verdict.step_reward = step_reward
            return verdict

        # Handle assertion action
        if action_type == "assert":
            verdict = self._verify_assertion(
                test_goal=test_goal,
                assertion=action.get("params", {}).get("condition", action_desc),
                step_number=step_number,
                screenshot_path=screenshot_path,
                ui_xml_summary=ui_xml_summary
            )
            # Add subgoal detection and reward calculation for assertions too
            subgoals_achieved = []
            step_reward = None
            if self.subgoal_decomposition and self.reward_calculator:
                subgoals_achieved = self.detect_subgoals_achieved(
                    step_number=step_number,
                    action=action,
                    execution_result=execution_result,
                    screenshot_path=screenshot_path,
                    ui_xml_summary=ui_xml_summary
                )
                step_reward = self.reward_calculator.calculate_step_reward(
                    step_number=step_number,
                    subgoals_achieved_this_step=subgoals_achieved
                )
            verdict.subgoals_achieved_this_step = subgoals_achieved
            verdict.step_reward = step_reward
            return verdict

        # Regular action succeeded, continue
        # NEW: Detect subgoals achieved and calculate rewards
        subgoals_achieved = []
        step_reward = None

        if self.subgoal_decomposition and self.reward_calculator:
            subgoals_achieved = self.detect_subgoals_achieved(
                step_number=step_number,
                action=action,
                execution_result=execution_result,
                screenshot_path=screenshot_path,
                ui_xml_summary=ui_xml_summary
            )

            # Calculate step reward
            step_reward = self.reward_calculator.calculate_step_reward(
                step_number=step_number,
                subgoals_achieved_this_step=subgoals_achieved
            )

        return TestVerdict(
            verdict=VerdictType.RUNNING,
            reason=f"Step {step_number} completed: {action_desc}",
            step_number=step_number,
            subgoals_achieved_this_step=subgoals_achieved,
            step_reward=step_reward
        )

    def detect_subgoals_achieved(
        self,
        step_number: int,
        action: Dict[str, Any],
        execution_result: ExecutionResult,
        screenshot_path: str,
        ui_xml_summary: str
    ) -> List[str]:
        """
        Detect which pending subgoals have been achieved in this step.

        Args:
            step_number: Current step number
            action: Action that was executed
            execution_result: Result of action execution
            screenshot_path: Post-action screenshot
            ui_xml_summary: Post-action UI state

        Returns:
            List of subgoal IDs that were achieved this step
        """
        if not self.subgoal_decomposition:
            return []

        achieved_subgoals = []
        pending_subgoals = [
            sg for sg in self.subgoal_decomposition.subgoals
            if sg.status == SubgoalStatus.PENDING
        ]

        if not pending_subgoals:
            return []

        # Build context for LLM detection
        pending_descriptions = "\n".join([
            f"- {sg.id}: {sg.description} (Detection: {sg.detection_criteria})"
            for sg in pending_subgoals
        ])

        prompt = f"""You are evaluating whether any pending subgoals were achieved in this test step.

ACTION EXECUTED: {action.get('action_type')} - {action.get('description')}
EXECUTION SUCCESS: {execution_result.success}
EXECUTION MESSAGE: {execution_result.message}

PENDING SUBGOALS:
{pending_descriptions}

CURRENT UI STATE:
{ui_xml_summary}

Based on the action executed, execution result, screenshot, and current UI state, determine which (if any) of the pending subgoals have been ACHIEVED in this step.

DETECTION RULES:
1. A subgoal is achieved if its detection criteria are MET (e.g., UI element visible, action completed)
2. Be CONSERVATIVE - only mark as achieved if there's clear evidence
3. Subgoals are typically achieved in order, but not always
4. Multiple subgoals can be achieved in a single step
5. If uncertain, do NOT mark as achieved (wait for more evidence)

Examples for Obsidian tasks:
- Subgoal "Obsidian app opened" is achieved if Obsidian main screen or vault list is visible in UI state
- Subgoal "Vault creation initiated" is achieved if tap on create vault button succeeded
- Subgoal "Note creation initiated" is achieved if action was tap_by_text on 'Create new note' and execution succeeded
- Subgoal "Title field populated" is achieved if input_text action succeeded with field_type='title' and correct text
- Subgoal "Body field populated" is achieved if input_text action succeeded with field_type='body' and correct text
- Subgoal "Settings accessed" is achieved if UI state shows Settings screen with options like "Appearance", "About", etc.
- Subgoal "Inside vault view" is achieved if UI shows 'Create new note' button or empty vault screen

Respond with JSON:
{{
    "achieved_subgoals": [
        {{
            "id": "subgoal_X",
            "confidence": 0.95,
            "reason": "Brief explanation of why this subgoal is achieved"
        }},
        ...
    ]
}}

If NO subgoals were achieved, return empty list:
{{
    "achieved_subgoals": []
}}

Respond with valid JSON only:"""

        try:
            result = self.llm.generate_json(
                prompt=prompt,
                image_path=screenshot_path,
                temperature=0.2
            )

            for achieved in result.get("achieved_subgoals", []):
                subgoal_id = achieved.get("id")
                confidence = achieved.get("confidence", 0.0)
                reason = achieved.get("reason", "")

                # Find and update the subgoal
                for sg in self.subgoal_decomposition.subgoals:
                    if sg.id == subgoal_id and sg.status == SubgoalStatus.PENDING:
                        sg.status = SubgoalStatus.ACHIEVED
                        sg.achieved_at_step = step_number
                        sg.confidence = confidence
                        achieved_subgoals.append(subgoal_id)
                        print(f"  ✓ Subgoal achieved: {sg.description} (confidence: {confidence:.2f})")
                        break

            return achieved_subgoals

        except Exception as e:
            print(f"  Warning: Subgoal detection failed: {e}")
            return []

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
