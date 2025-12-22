"""
Main CLI for mobile QA multiagent system.
"""
import argparse
import hashlib
import json
import time
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

from .tools.adb import ADB, ADBError
from .tools.uixml import UIXMLParser
from .llm.gemini_client import GeminiClient
from .agents.planner import PlannerAgent
from .agents.executor import ExecutorAgent
from .agents.supervisor import SupervisorAgent, VerdictType
from .evaluation.subgoals import SubgoalDecomposer, RewardCalculator, SubgoalStatus


class MobileQARunner:
    """Main test runner orchestrating Supervisor-Planner-Executor system."""

    def __init__(
        self,
        device_id: str,
        model: str = "gemini-2.0-flash-exp",
        artifacts_dir: str = "artifacts"
    ):
        """
        Initialize MobileQA runner.

        Args:
            device_id: Android device serial number
            model: LLM model to use
            artifacts_dir: Directory to save artifacts
        """
        self.device_id = device_id
        self.artifacts_dir = Path(artifacts_dir)

        # Initialize tools
        self.adb = ADB(device_id=device_id)
        self.ui_parser = UIXMLParser(self.adb)

        # Initialize LLM client
        self.llm = GeminiClient(model=model)

        # Initialize agents
        self.planner = PlannerAgent(self.llm)
        self.executor = ExecutorAgent(self.adb, self.ui_parser)
        self.supervisor = SupervisorAgent(self.llm)

    def handle_common_popups(self, ui_xml_path: str, step_dir: Path, max_attempts: int = 5) -> bool:
        """
        Handle common onboarding popups deterministically.

        Args:
            ui_xml_path: Path to UI XML file
            step_dir: Step artifacts directory
            max_attempts: Maximum popup handling attempts

        Returns:
            True if any popup was handled
        """
        popup_texts = [
            "Allow", "ALLOW", "While using the app", "Continue",
            "Continue without sync", "Not now", "OK", "Got it",
            "USE THIS FOLDER", "Grant", "Permit"
        ]

        handled_any = False
        tapped_locations = set()  # Track tapped locations to avoid infinite loops

        for attempt in range(max_attempts):
            # Parse current UI
            nodes = self.ui_parser.parse_xml(ui_xml_path)

            # Look for popup texts
            found_popup = False
            for popup_text in popup_texts:
                matches = self.ui_parser.find_by_text(nodes, popup_text, exact=False)
                if matches:
                    # Get center of first match
                    x, y = matches[0].center
                    location_key = f"{popup_text}_{x}_{y}"

                    # Skip if we already tapped this exact location
                    if location_key in tapped_locations:
                        continue

                    # Tap the element
                    print(f"  Auto-handling popup: '{popup_text}' at ({x}, {y})")
                    self.adb.tap_xy(x, y, wait_after=0.3)  # SUPER FAST
                    handled_any = True
                    found_popup = True
                    tapped_locations.add(location_key)
                    break

            if not found_popup:
                # No more popups found
                break

            # Wait and refresh UI dump for next iteration
            time.sleep(0.2)  # SUPER FAST
            self.ui_parser.dump_ui(ui_xml_path)

        # Save artifact note if we handled popups
        if handled_any:
            with open(step_dir / "auto_handled_popup.txt", 'w') as f:
                f.write(f"auto_handled_popup=true\nTapped locations: {len(tapped_locations)}\n")
            # Extra wait after handling popups to let UI fully settle
            time.sleep(0.3)  # SUPER FAST
            # Refresh UI dump one final time
            self.ui_parser.dump_ui(ui_xml_path)

        return handled_any

    def setup_app(self, apk_path: str, package_name: str, clear_data: bool = True):
        """
        Setup app for testing.

        Args:
            apk_path: Path to APK file
            package_name: App package name
            clear_data: Whether to clear app data before testing
        """
        print(f"Setting up app: {package_name}")

        # Install APK
        if apk_path:
            print(f"Installing APK: {apk_path}")
            self.adb.install_apk(apk_path, replace=True)

        # Clear app data if requested
        if clear_data:
            print(f"Clearing app data for: {package_name}")
            self.adb.clear_app_data(package_name)

        # Launch app
        print(f"Launching app: {package_name}")
        self.adb.start_activity(package_name)
        #time.sleep(0.5)  # SUPER FAST - minimal wait for app to start

    def run_test(self, test_config: Dict[str, Any], reset_app: bool = False) -> Dict[str, Any]:
        """
        Run a single test.

        Args:
            test_config: Test configuration dictionary
            reset_app: Whether to clear app data before testing

        Returns:
            Test result dictionary
        """
        test_name = test_config['name']
        test_goal = test_config['goal']
        package_name = test_config.get('package', 'md.obsidian')
        setup_steps = test_config.get('setup', [])

        print(f"\n{'='*60}")
        print(f"Running test: {test_name}")
        print(f"Goal: {test_goal}")
        print(f"{'='*60}\n")

        # Create test artifacts directory
        test_artifacts_dir = self.artifacts_dir / test_name
        test_artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Setup app
        apk_path = test_config.get('apk_path')
        self.setup_app(apk_path, package_name, clear_data=reset_app)

        # Execute setup steps if any
        if setup_steps:
            print("Executing setup steps...")
            for step_desc in setup_steps:
                print(f"  - {step_desc}")
                # Simple setup step execution (could be enhanced)
                #time.sleep(0.5)

        # NEW: Decompose test goal into subgoals
        print("\nDecomposing test goal into subgoals...")

        # Capture initial state for decomposition
        initial_screenshot = str(test_artifacts_dir / "initial_screenshot.png")
        initial_ui_xml = str(test_artifacts_dir / "initial_ui.xml")

        self.adb.screenshot(initial_screenshot)
        self.ui_parser.dump_ui(initial_ui_xml)
        initial_ui_summary = self.ui_parser.get_ui_summary(initial_ui_xml)

        # Decompose into subgoals
        decomposer = SubgoalDecomposer(self.llm)
        subgoal_decomposition = decomposer.decompose_test_goal(
            test_goal=test_goal,
            screenshot_path=initial_screenshot,
            ui_xml_summary=initial_ui_summary
        )

        # Save subgoal decomposition
        with open(test_artifacts_dir / "subgoals.json", 'w') as f:
            json.dump({
                'test_goal': test_goal,
                'subgoals': [
                    {
                        'id': sg.id,
                        'description': sg.description,
                        'detection_criteria': sg.detection_criteria,
                        'status': sg.status.value
                    }
                    for sg in subgoal_decomposition.subgoals
                ]
            }, f, indent=2)

        print(f"Identified {len(subgoal_decomposition.subgoals)} subgoals:")
        for sg in subgoal_decomposition.subgoals:
            print(f"  - {sg.description}")

        # Initialize reward calculator
        reward_calculator = RewardCalculator(
            total_subgoals=len(subgoal_decomposition.subgoals)
        )

        # Update supervisor with subgoal decomposition and reward calculator
        self.supervisor.subgoal_decomposition = subgoal_decomposition
        self.supervisor.reward_calculator = reward_calculator

        # Run test steps
        step_number = 0
        previous_actions = []
        final_verdict = None
        step_rewards = []  # NEW: Track step rewards

        # State tracking for loop detection
        ui_state_hashes = []
        unchanged_count = 0
        recovery_attempt = 0

        while step_number < self.supervisor.max_steps:
            step_number += 1
            print(f"\n--- Step {step_number} ---")

            # Create step artifacts directory
            step_dir = test_artifacts_dir / f"step_{step_number:02d}"
            step_dir.mkdir(parents=True, exist_ok=True)

            # Capture current state
            screenshot_path = str(step_dir / "screenshot.png")
            ui_xml_path = str(step_dir / "ui.xml")

            print("Capturing screenshot...")
            self.adb.screenshot(screenshot_path)

            print("Dumping UI hierarchy...")
            self.ui_parser.dump_ui(ui_xml_path)
            ui_summary = self.ui_parser.get_ui_summary(ui_xml_path)

            # Save UI summary
            with open(step_dir / "ui_summary.txt", 'w') as f:
                f.write(ui_summary)

            # Handle common popups before planning
            print("Checking for common popups...")
            handled_popup = self.handle_common_popups(ui_xml_path, step_dir)
            if handled_popup:
                # Refresh UI after handling popups
                self.ui_parser.dump_ui(ui_xml_path)
                ui_summary = self.ui_parser.get_ui_summary(ui_xml_path)
                with open(step_dir / "ui_summary.txt", 'w') as f:
                    f.write(ui_summary)

            # Compute UI state hash for loop detection
            ui_hash = hashlib.md5(ui_summary.encode()).hexdigest()
            ui_state_hashes.append(ui_hash)

            # Check for unchanged UI (loop detection)
            if len(ui_state_hashes) >= 3:
                last_three = ui_state_hashes[-3:]
                if len(set(last_three)) == 1:  # All same
                    unchanged_count += 1
                    print(f"WARNING: UI unchanged for {unchanged_count} consecutive checks")

                    if unchanged_count >= 3:
                        # UI is stuck, attempt recovery
                        recovery_attempt += 1
                        print(f"UI stuck detected. Recovery attempt {recovery_attempt}/3")

                        if recovery_attempt == 1:
                            print("Recovery: waiting 2 seconds...")
                            time.sleep(2)
                        elif recovery_attempt == 2:
                            print("Recovery: pressing BACK...")
                            self.adb.keyevent(4, wait_after=1.5)
                        elif recovery_attempt >= 3:
                            print("Recovery: HOME and relaunch...")
                            self.adb.keyevent(3, wait_after=1.0)
                            self.adb.start_activity(package_name, wait_after=2.0)

                            # Check if still stuck after relaunch
                            self.ui_parser.dump_ui(ui_xml_path)
                            new_ui_summary = self.ui_parser.get_ui_summary(ui_xml_path)
                            new_hash = hashlib.md5(new_ui_summary.encode()).hexdigest()

                            if new_hash == ui_hash:
                                # Still stuck after all recovery attempts
                                from .agents.supervisor import TestVerdict
                                final_verdict = TestVerdict(
                                    verdict=VerdictType.FAIL_ACTION,
                                    reason="UI stuck - unchanged after recovery attempts",
                                    step_number=step_number,
                                    details="UI state did not change for 3+ steps despite recovery"
                                )
                                break

                        # Reset UI state tracking after recovery
                        ui_state_hashes = []
                        unchanged_count = 0
                        continue
                else:
                    unchanged_count = 0
                    recovery_attempt = 0

            # Plan next action
            print("Planning next action...")
            action = self.planner.plan_next_action(
                test_goal=test_goal,
                current_step=step_number,
                screenshot_path=screenshot_path,
                ui_xml_summary=ui_summary,
                previous_actions=previous_actions
            )

            # Validate action schema
            is_valid, validation_error = self.planner.validate_action_schema(action)

            # Additional validation: check if tap_by_text text is visible in UI
            if is_valid and action.get('action_type') == 'tap_by_text':
                tap_text = action.get('params', {}).get('text', '')
                if tap_text and tap_text.lower() not in ui_summary.lower():
                    is_valid = False
                    validation_error = f"tap_by_text text '{tap_text}' not found in current UI state. Available UI contains different text."

            if not is_valid:
                print(f"WARNING: Invalid action schema - {validation_error}")

                # Save validation error
                with open(step_dir / "validation_error.txt", 'w') as f:
                    f.write(f"Invalid action schema: {validation_error}\n")
                    f.write(f"Action received: {json.dumps(action, indent=2)}\n")

                # Attempt replan with error feedback
                print("Replanning with error feedback...")
                replan_prompt_addition = f"\n\nYour last action was INVALID: {validation_error}\nYou MUST output valid JSON with correct action_type and params. Review the schema carefully."

                # Create a modified ui_summary with error message
                replan_ui_summary = ui_summary + replan_prompt_addition

                action = self.planner.plan_next_action(
                    test_goal=test_goal,
                    current_step=step_number,
                    screenshot_path=screenshot_path,
                    ui_xml_summary=replan_ui_summary,
                    previous_actions=previous_actions
                )

                # Validate again
                is_valid_retry, validation_error_retry = self.planner.validate_action_schema(action)
                if not is_valid_retry:
                    print(f"ERROR: Replan still invalid - {validation_error_retry}")

                    # Save final validation error
                    with open(step_dir / "validation_error_final.txt", 'w') as f:
                        f.write(f"Replan failed: {validation_error_retry}\n")
                        f.write(f"Action received: {json.dumps(action, indent=2)}\n")

                    # Mark as FAIL_ACTION
                    from .agents.supervisor import TestVerdict
                    final_verdict = TestVerdict(
                        verdict=VerdictType.FAIL_ACTION,
                        reason="Invalid action schema after replan",
                        step_number=step_number,
                        details=f"Planner output invalid action twice: {validation_error_retry}"
                    )
                    break

            # Save action
            with open(step_dir / "action.json", 'w') as f:
                json.dump(action, f, indent=2)

            print(f"Action: {action['action_type']} - {action['description']}")

            # Execute action
            print("Executing action...")
            exec_result = self.executor.execute_action(action)
            print(f"Execution: {exec_result.message}")

            # Save execution result
            with open(step_dir / "execution_result.json", 'w') as f:
                json.dump({
                    'success': exec_result.success,
                    'message': exec_result.message,
                    'error': exec_result.error
                }, f, indent=2)

            # Update previous actions
            previous_actions.append(action)

            # Wait for UI to settle after action
            if exec_result.success and action['action_type'] not in ['wait', 'done']:
                time.sleep(1)

            # Capture post-action state
            post_screenshot_path = str(step_dir / "screenshot_post.png")
            post_ui_xml_path = str(step_dir / "ui_post.xml")

            self.adb.screenshot(post_screenshot_path)
            self.ui_parser.dump_ui(post_ui_xml_path)
            post_ui_summary = self.ui_parser.get_ui_summary(post_ui_xml_path)

            # Supervise and get verdict
            print("Evaluating step...")
            verdict = self.supervisor.evaluate_step(
                test_goal=test_goal,
                step_number=step_number,
                action=action,
                execution_result=exec_result,
                screenshot_path=post_screenshot_path,
                ui_xml_summary=post_ui_summary
            )

            # NEW: Collect step reward
            if verdict.step_reward:
                step_rewards.append(verdict.step_reward)
                print(f"Step reward: {verdict.step_reward.step_penalty + verdict.step_reward.subgoal_reward:.3f} "
                      f"(cumulative: {verdict.step_reward.cumulative_reward:.3f})")

            # Save verdict with subgoal and reward info
            with open(step_dir / "verdict.json", 'w') as f:
                verdict_data = {
                    'verdict': verdict.verdict.value,
                    'reason': verdict.reason,
                    'step_number': verdict.step_number,
                    'details': verdict.details,
                    'subgoals_achieved': verdict.subgoals_achieved_this_step,
                }
                if verdict.step_reward:
                    verdict_data['step_reward'] = {
                        'step_penalty': verdict.step_reward.step_penalty,
                        'subgoal_reward': verdict.step_reward.subgoal_reward,
                        'cumulative_reward': verdict.step_reward.cumulative_reward,
                        'subgoals_achieved_count': verdict.step_reward.total_subgoals_achieved,
                        'total_subgoals': verdict.step_reward.total_subgoals
                    }
                json.dump(verdict_data, f, indent=2)

            print(f"Verdict: {verdict.verdict.value} - {verdict.reason}")

            # Check if test is complete
            if verdict.verdict != VerdictType.RUNNING:
                final_verdict = verdict
                break

        # Handle case where max steps reached without verdict
        if final_verdict is None:
            from .agents.supervisor import TestVerdict
            final_verdict = TestVerdict(
                verdict=VerdictType.FAIL_ACTION,
                reason=f"Test exceeded maximum steps ({self.supervisor.max_steps})",
                step_number=step_number,
                details="Test did not complete within step limit"
            )

        # Print final verdict
        print(f"\n{self.supervisor.format_verdict(final_verdict)}")

        # NEW: Calculate final reward
        test_passed = (final_verdict.verdict == VerdictType.PASS)
        reward_summary = reward_calculator.calculate_final_reward(
            total_steps=step_number,
            test_passed=test_passed,
            step_rewards=step_rewards
        )

        # Save final subgoal status
        with open(test_artifacts_dir / "subgoals_final.json", 'w') as f:
            json.dump({
                'test_goal': test_goal,
                'subgoals': [
                    {
                        'id': sg.id,
                        'description': sg.description,
                        'status': sg.status.value,
                        'achieved_at_step': sg.achieved_at_step,
                        'confidence': sg.confidence
                    }
                    for sg in subgoal_decomposition.subgoals
                ]
            }, f, indent=2)

        # Save reward summary
        with open(test_artifacts_dir / "reward_summary.json", 'w') as f:
            json.dump({
                'total_steps': reward_summary.total_steps,
                'total_step_penalty': reward_summary.total_step_penalty,
                'total_subgoal_reward': reward_summary.total_subgoal_reward,
                'completion_bonus': reward_summary.completion_bonus,
                'final_reward': reward_summary.final_reward,
                'subgoals_achieved': reward_summary.subgoals_achieved,
                'total_subgoals': reward_summary.total_subgoals,
                'subgoal_completion_rate': reward_summary.subgoal_completion_rate,
                'step_rewards': [
                    {
                        'step': sr.step_number,
                        'penalty': sr.step_penalty,
                        'reward': sr.subgoal_reward,
                        'cumulative': sr.cumulative_reward
                    }
                    for sr in reward_summary.step_rewards
                ]
            }, f, indent=2)

        # Print reward summary
        print(f"\n{'='*60}")
        print("REWARD SUMMARY")
        print(f"{'='*60}")
        print(f"Total Steps: {reward_summary.total_steps}")
        print(f"Step Penalty: {reward_summary.total_step_penalty:.3f}")
        print(f"Subgoal Reward: {reward_summary.total_subgoal_reward:.3f} ({reward_summary.subgoals_achieved}/{reward_summary.total_subgoals} subgoals)")
        print(f"Completion Bonus: {reward_summary.completion_bonus:.3f}")
        print(f"Final Reward: {reward_summary.final_reward:.3f}")
        print(f"Subgoal Completion Rate: {reward_summary.subgoal_completion_rate:.1%}")
        print(f"{'='*60}\n")

        # Save final test result with reward info
        result = {
            'test_name': test_name,
            'verdict': final_verdict.verdict.value,
            'reason': final_verdict.reason,
            'details': final_verdict.details,
            'total_steps': step_number,
            'artifacts_dir': str(test_artifacts_dir),
            # NEW: Reward information
            'reward_summary': {
                'final_reward': reward_summary.final_reward,
                'step_penalty': reward_summary.total_step_penalty,
                'subgoal_reward': reward_summary.total_subgoal_reward,
                'completion_bonus': reward_summary.completion_bonus,
                'subgoals_achieved': reward_summary.subgoals_achieved,
                'total_subgoals': reward_summary.total_subgoals,
                'completion_rate': reward_summary.subgoal_completion_rate
            }
        }

        with open(test_artifacts_dir / "test_result.json", 'w') as f:
            json.dump(result, f, indent=2)

        return result

    def run_tests(self, tests_config: List[Dict[str, Any]], reset_app: bool = False) -> List[Dict[str, Any]]:
        """
        Run multiple tests.

        Args:
            tests_config: List of test configurations
            reset_app: Whether to clear app data before each test

        Returns:
            List of test results
        """
        results = []

        for test_config in tests_config:
            try:
                result = self.run_test(test_config, reset_app=reset_app)
                results.append(result)
            except Exception as e:
                print(f"ERROR running test {test_config['name']}: {str(e)}")
                results.append({
                    'test_name': test_config['name'],
                    'verdict': 'ERROR',
                    'reason': str(e),
                    'details': '',
                    'total_steps': 0
                })

        return results


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Mobile QA Multiagent System for Obsidian testing"
    )
    parser.add_argument(
        '--device',
        default='emulator-5554',
        help='Android device ID (default: emulator-5554)'
    )
    parser.add_argument(
        '--avd',
        help='AVD name to launch (optional)'
    )
    parser.add_argument(
        '--apk',
        help='Path to APK file to install'
    )
    parser.add_argument(
        '--tests',
        required=True,
        help='Path to tests YAML file'
    )
    parser.add_argument(
        '--model',
        default='gemini-2.0-flash-exp',
        help='LLM model to use (default: gemini-2.0-flash-exp)'
    )
    parser.add_argument(
        '--artifacts',
        default='artifacts',
        help='Artifacts directory (default: artifacts)'
    )
    parser.add_argument(
        '--reset-app',
        action='store_true',
        help='Clear app data before each test (forces onboarding)'
    )
    parser.add_argument(
        '--single-test',
        help='Run only a specific test by name'
    )

    args = parser.parse_args()

    # Load test configurations
    with open(args.tests, 'r') as f:
        config = yaml.safe_load(f)

    tests = config.get('tests', [])

    # Filter to single test if specified
    if args.single_test:
        tests = [t for t in tests if t['name'] == args.single_test]
        if not tests:
            print(f"ERROR: Test '{args.single_test}' not found in {args.tests}")
            return 1
        print(f"Running single test: {args.single_test}")

    # Add APK path to all tests if provided
    if args.apk:
        for test in tests:
            test['apk_path'] = args.apk

    # Initialize runner
    try:
        runner = MobileQARunner(
            device_id=args.device,
            model=args.model,
            artifacts_dir=args.artifacts
        )
    except Exception as e:
        print(f"ERROR initializing runner: {str(e)}")
        return 1

    # Run tests
    results = runner.run_tests(tests, reset_app=args.reset_app)

    # Print summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")

    pass_count = sum(1 for r in results if r['verdict'] == 'PASS')
    fail_action_count = sum(1 for r in results if r['verdict'] == 'FAIL_ACTION')
    fail_assertion_count = sum(1 for r in results if r['verdict'] == 'FAIL_ASSERTION')
    error_count = sum(1 for r in results if r['verdict'] == 'ERROR')

    for result in results:
        print(f"{result['test_name']}: {result['verdict']} - {result['reason']}")

    print(f"\nTotal: {len(results)} tests")
    print(f"PASS: {pass_count}")
    print(f"FAIL (Action): {fail_action_count}")
    print(f"FAIL (Assertion): {fail_assertion_count}")
    print(f"ERROR: {error_count}")
    print(f"{'='*60}\n")

    return 0 if error_count == 0 and fail_action_count == 0 and fail_assertion_count == 0 else 1


if __name__ == "__main__":
    exit(main())
