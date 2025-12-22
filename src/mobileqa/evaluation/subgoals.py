"""
Subgoal tracking and reward calculation for mobile QA tests.

This module provides LLM-based subgoal decomposition, automatic achievement detection,
and comprehensive reward scoring inspired by android_world_agents.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import json


class SubgoalStatus(Enum):
    """Status of a subgoal."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Subgoal:
    """Represents a single subgoal in the test execution."""
    id: str  # e.g., "subgoal_1", "subgoal_2"
    description: str  # Natural language description
    detection_criteria: str  # How to detect achievement (UI state, action)
    status: SubgoalStatus = SubgoalStatus.PENDING
    achieved_at_step: Optional[int] = None
    confidence: float = 0.0  # LLM confidence in achievement (0.0-1.0)


@dataclass
class SubgoalDecomposition:
    """Result of LLM-based test goal decomposition."""
    test_goal: str
    subgoals: List[Subgoal] = field(default_factory=list)
    decomposition_timestamp: Optional[str] = None


@dataclass
class StepReward:
    """Reward information for a single step."""
    step_number: int
    step_penalty: float = -0.05  # Constant penalty per step
    subgoal_reward: float = 0.0  # +0.2 if subgoal achieved
    subgoals_achieved_this_step: List[str] = field(default_factory=list)
    cumulative_reward: float = 0.0
    total_subgoals_achieved: int = 0
    total_subgoals: int = 0


@dataclass
class RewardSummary:
    """Final reward summary for test execution."""
    total_steps: int
    total_step_penalty: float  # steps × -0.05
    total_subgoal_reward: float  # subgoals_achieved × +0.2
    completion_bonus: float  # +1.0 if PASS, 0.0 otherwise
    final_reward: float
    subgoals_achieved: int
    total_subgoals: int
    subgoal_completion_rate: float  # achieved / total
    step_rewards: List[StepReward] = field(default_factory=list)


class SubgoalDecomposer:
    """Handles LLM-based subgoal decomposition."""

    def __init__(self, llm_client):
        """
        Initialize SubgoalDecomposer.

        Args:
            llm_client: GeminiClient instance for LLM calls
        """
        self.llm = llm_client

    def decompose_test_goal(
        self,
        test_goal: str,
        screenshot_path: str,
        ui_xml_summary: str
    ) -> SubgoalDecomposition:
        """
        Decompose test goal into measurable subgoals using LLM.

        Args:
            test_goal: High-level test objective
            screenshot_path: Initial app screenshot
            ui_xml_summary: Initial UI state

        Returns:
            SubgoalDecomposition with list of subgoals
        """
        prompt = f"""You are analyzing a mobile app test goal to break it down into measurable intermediate subgoals.

TEST GOAL:
{test_goal}

INITIAL UI STATE:
{ui_xml_summary}

Your task is to decompose this test goal into 3-7 concrete, measurable subgoals that represent progress toward the final goal.

SUBGOAL DESIGN PRINCIPLES:
1. Each subgoal should be DETECTABLE through UI state changes or specific actions
2. Subgoals should be SEQUENTIAL (earlier ones typically achieved before later ones)
3. Subgoals should be ATOMIC (single observable achievement)
4. Include both ACTION subgoals (e.g., "Open Settings menu") and STATE subgoals (e.g., "Settings screen is visible")

EXAMPLES FOR OBSIDIAN TASKS:

Test Goal: "Open Obsidian, create a new Vault named 'InternVault', and enter the vault"
Subgoals:
1. "Obsidian app opened" - Detected when Obsidian main screen or vault list is visible
2. "Vault creation initiated" - Detected when create vault button/option is tapped
3. "Storage location selected" - Detected when folder picker appears or location is confirmed
4. "Vault name entered" - Detected when 'InternVault' text is typed in name field
5. "Vault creation confirmed" - Detected when create/confirm button is tapped
6. "Inside vault view" - Detected when 'Create new note' button appears or empty vault screen shown

Test Goal: "Create a new note titled 'Meeting Notes' and type the text 'Daily Standup' into the body"
Subgoals:
1. "Note creation initiated" - Detected when 'Create new note' button is tapped
2. "Note editor opened" - Detected when note editing screen with title and body fields is visible
3. "Title field populated" - Detected when 'Meeting Notes' is typed in title field (top field)
4. "Focus moved to body" - Detected when cursor moves to body field after title input
5. "Body field populated" - Detected when 'Daily Standup' is typed in body field
6. "Note content saved" - Detected when note shows both title and body correctly

Test Goal: "Go to Settings and verify that the 'Appearance' tab icon is the color Red"
Subgoals:
1. "Sidebar opened" - Detected when sidebar menu appears (gear icon or menu visible)
2. "Settings accessed" - Detected when Settings option is tapped
3. "Settings screen visible" - Detected when Settings menu with options appears
4. "Appearance section visible" - Detected when Appearance option is shown in Settings
5. "Appearance verification" - Detected when checking Appearance icon color via assert action

Test Goal: "Find and click the 'Print to PDF' button in the main file menu"
Subgoals:
1. "Note opened" - Detected when a note is open and visible
2. "File menu accessed" - Detected when 3-dot menu or more options is tapped
3. "Menu options visible" - Detected when menu options are displayed
4. "Search for Print option" - Detected when looking through menu items for 'Print to PDF'
5. "Report not found" - Detected when 'fail' action is used (Print to PDF doesn't exist in mobile)

For the given test goal, provide a JSON response with this structure:
{{
    "subgoals": [
        {{
            "id": "subgoal_1",
            "description": "Brief description of what is achieved",
            "detection_criteria": "How to detect this subgoal (e.g., 'UI shows X', 'Action Y executed', 'Text Z visible')"
        }},
        ...
    ]
}}

Respond with valid JSON only:"""

        try:
            result = self.llm.generate_json(
                prompt=prompt,
                image_path=screenshot_path,
                temperature=0.3
            )

            subgoals = []
            for sg_data in result.get("subgoals", []):
                subgoal = Subgoal(
                    id=sg_data.get("id", f"subgoal_{len(subgoals)+1}"),
                    description=sg_data.get("description", ""),
                    detection_criteria=sg_data.get("detection_criteria", ""),
                    status=SubgoalStatus.PENDING
                )
                subgoals.append(subgoal)

            return SubgoalDecomposition(
                test_goal=test_goal,
                subgoals=subgoals,
                decomposition_timestamp=datetime.now().isoformat()
            )

        except Exception as e:
            print(f"Warning: Subgoal decomposition failed: {e}")
            print("Falling back to single generic subgoal")
            # Fallback: Create a single generic subgoal
            return SubgoalDecomposition(
                test_goal=test_goal,
                subgoals=[
                    Subgoal(
                        id="subgoal_generic",
                        description="Complete test goal",
                        detection_criteria="Test marked as done",
                        status=SubgoalStatus.PENDING
                    )
                ],
                decomposition_timestamp=datetime.now().isoformat()
            )


class RewardCalculator:
    """Calculates rewards based on steps, subgoals, and completion."""

    STEP_PENALTY = -0.05
    SUBGOAL_REWARD = 0.2
    COMPLETION_BONUS = 1.0

    def __init__(self, total_subgoals: int):
        """
        Initialize RewardCalculator.

        Args:
            total_subgoals: Total number of subgoals for the test
        """
        self.total_subgoals = total_subgoals
        self.cumulative_reward = 0.0
        self.total_subgoals_achieved = 0

    def calculate_step_reward(
        self,
        step_number: int,
        subgoals_achieved_this_step: List[str]
    ) -> StepReward:
        """
        Calculate reward for a single step.

        Args:
            step_number: Current step number
            subgoals_achieved_this_step: List of subgoal IDs achieved in this step

        Returns:
            StepReward with penalty, reward, and cumulative info
        """
        step_penalty = self.STEP_PENALTY
        subgoal_reward = len(subgoals_achieved_this_step) * self.SUBGOAL_REWARD

        self.total_subgoals_achieved += len(subgoals_achieved_this_step)
        self.cumulative_reward += step_penalty + subgoal_reward

        return StepReward(
            step_number=step_number,
            step_penalty=step_penalty,
            subgoal_reward=subgoal_reward,
            subgoals_achieved_this_step=subgoals_achieved_this_step,
            cumulative_reward=self.cumulative_reward,
            total_subgoals_achieved=self.total_subgoals_achieved,
            total_subgoals=self.total_subgoals
        )

    def calculate_final_reward(
        self,
        total_steps: int,
        test_passed: bool,
        step_rewards: List[StepReward]
    ) -> RewardSummary:
        """
        Calculate final reward summary.

        Args:
            total_steps: Total number of steps executed
            test_passed: Whether test resulted in PASS verdict
            step_rewards: List of all step rewards

        Returns:
            RewardSummary with final calculations
        """
        total_step_penalty = total_steps * self.STEP_PENALTY
        total_subgoal_reward = self.total_subgoals_achieved * self.SUBGOAL_REWARD
        completion_bonus = self.COMPLETION_BONUS if test_passed else 0.0

        final_reward = total_step_penalty + total_subgoal_reward + completion_bonus

        subgoal_completion_rate = (
            self.total_subgoals_achieved / self.total_subgoals
            if self.total_subgoals > 0 else 0.0
        )

        return RewardSummary(
            total_steps=total_steps,
            total_step_penalty=total_step_penalty,
            total_subgoal_reward=total_subgoal_reward,
            completion_bonus=completion_bonus,
            final_reward=final_reward,
            subgoals_achieved=self.total_subgoals_achieved,
            total_subgoals=self.total_subgoals,
            subgoal_completion_rate=subgoal_completion_rate,
            step_rewards=step_rewards
        )
