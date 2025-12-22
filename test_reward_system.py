#!/usr/bin/env python3
"""
Test script to verify the reward evaluation system implementation.

This script tests the subgoal decomposition and reward calculation components
in isolation before running full end-to-end tests.
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all new modules can be imported."""
    print("Testing imports...")
    try:
        from mobileqa.evaluation.subgoals import (
            SubgoalStatus,
            Subgoal,
            SubgoalDecomposition,
            StepReward,
            RewardSummary,
            SubgoalDecomposer,
            RewardCalculator
        )
        print("✓ All evaluation modules imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_data_structures():
    """Test that data structures can be instantiated."""
    print("\nTesting data structures...")
    try:
        from mobileqa.evaluation.subgoals import (
            Subgoal,
            SubgoalDecomposition,
            StepReward,
            RewardSummary,
            SubgoalStatus
        )

        # Test Subgoal
        sg = Subgoal(
            id="test_1",
            description="Test subgoal",
            detection_criteria="Test criteria"
        )
        assert sg.status == SubgoalStatus.PENDING
        print("  ✓ Subgoal dataclass works")

        # Test SubgoalDecomposition
        decomp = SubgoalDecomposition(
            test_goal="Test goal",
            subgoals=[sg]
        )
        assert len(decomp.subgoals) == 1
        print("  ✓ SubgoalDecomposition dataclass works")

        # Test StepReward
        sr = StepReward(
            step_number=1,
            step_penalty=-0.05,
            subgoal_reward=0.2,
            subgoals_achieved_this_step=["test_1"],
            cumulative_reward=0.15
        )
        assert sr.cumulative_reward == 0.15
        print("  ✓ StepReward dataclass works")

        # Test RewardSummary
        rs = RewardSummary(
            total_steps=5,
            total_step_penalty=-0.25,
            total_subgoal_reward=0.4,
            completion_bonus=1.0,
            final_reward=1.15,
            subgoals_achieved=2,
            total_subgoals=3,
            subgoal_completion_rate=0.667,
            step_rewards=[sr]
        )
        assert rs.final_reward == 1.15
        print("  ✓ RewardSummary dataclass works")

        return True
    except Exception as e:
        print(f"  ✗ Data structure test failed: {e}")
        return False


def test_reward_calculator():
    """Test RewardCalculator logic."""
    print("\nTesting RewardCalculator...")
    try:
        from mobileqa.evaluation.subgoals import RewardCalculator

        # Test step reward calculation
        calc = RewardCalculator(total_subgoals=5)

        # Helper function for approximate equality
        def approx_equal(a, b, epsilon=0.001):
            return abs(a - b) < epsilon

        # Step 1: 1 subgoal achieved
        sr1 = calc.calculate_step_reward(1, ["sg_1"])
        assert sr1.step_penalty == -0.05
        assert sr1.subgoal_reward == 0.2
        assert approx_equal(sr1.cumulative_reward, 0.15)
        assert sr1.total_subgoals_achieved == 1
        print("  ✓ Step 1 reward calculation correct")

        # Step 2: 2 subgoals achieved
        sr2 = calc.calculate_step_reward(2, ["sg_2", "sg_3"])
        assert sr2.subgoal_reward == 0.4
        assert approx_equal(sr2.cumulative_reward, 0.5)  # 0.15 + (-0.05 + 0.4)
        assert sr2.total_subgoals_achieved == 3
        print("  ✓ Step 2 reward calculation correct")

        # Test final reward calculation (PASS)
        summary_pass = calc.calculate_final_reward(
            total_steps=5,
            test_passed=True,
            step_rewards=[sr1, sr2]
        )
        assert summary_pass.total_steps == 5
        assert approx_equal(summary_pass.total_step_penalty, -0.25)  # 5 * -0.05
        assert approx_equal(summary_pass.total_subgoal_reward, 0.6)  # 3 * 0.2
        assert summary_pass.completion_bonus == 1.0
        assert approx_equal(summary_pass.final_reward, 1.35)  # -0.25 + 0.6 + 1.0
        print("  ✓ Final reward calculation (PASS) correct")

        # Test final reward calculation (FAIL)
        calc2 = RewardCalculator(total_subgoals=5)
        calc2.total_subgoals_achieved = 2
        summary_fail = calc2.calculate_final_reward(
            total_steps=8,
            test_passed=False,
            step_rewards=[]
        )
        assert approx_equal(summary_fail.total_step_penalty, -0.4)  # 8 * -0.05
        assert approx_equal(summary_fail.total_subgoal_reward, 0.4)  # 2 * 0.2
        assert summary_fail.completion_bonus == 0.0
        assert approx_equal(summary_fail.final_reward, 0.0)  # -0.4 + 0.4 + 0.0
        print("  ✓ Final reward calculation (FAIL) correct")

        return True
    except Exception as e:
        print(f"  ✗ RewardCalculator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_supervisor_integration():
    """Test that SupervisorAgent can be initialized with new parameters."""
    print("\nTesting SupervisorAgent integration...")
    try:
        from mobileqa.agents.supervisor import SupervisorAgent, TestVerdict, VerdictType
        from mobileqa.evaluation.subgoals import (
            SubgoalDecomposition,
            Subgoal,
            RewardCalculator
        )

        # Mock LLM client
        class MockLLM:
            def generate_json(self, *args, **kwargs):
                return {}

        # Create subgoal decomposition
        decomp = SubgoalDecomposition(
            test_goal="Test",
            subgoals=[
                Subgoal(id="sg_1", description="Test 1", detection_criteria="Criteria 1"),
                Subgoal(id="sg_2", description="Test 2", detection_criteria="Criteria 2"),
            ]
        )

        # Create reward calculator
        calc = RewardCalculator(total_subgoals=2)

        # Initialize supervisor with new parameters
        supervisor = SupervisorAgent(
            llm_client=MockLLM(),
            max_steps=30,
            subgoal_decomposition=decomp,
            reward_calculator=calc
        )

        assert supervisor.subgoal_decomposition is not None
        assert supervisor.reward_calculator is not None
        print("  ✓ SupervisorAgent accepts new parameters")

        # Test TestVerdict with new fields
        verdict = TestVerdict(
            verdict=VerdictType.RUNNING,
            reason="Test",
            step_number=1,
            details="Details",
            subgoals_achieved_this_step=["sg_1"]
        )
        assert verdict.subgoals_achieved_this_step == ["sg_1"]
        print("  ✓ TestVerdict has new fields")

        return True
    except Exception as e:
        print(f"  ✗ SupervisorAgent integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("REWARD SYSTEM VERIFICATION TESTS")
    print("="*60)

    results = []

    # Run tests
    results.append(("Import Test", test_imports()))
    results.append(("Data Structures Test", test_data_structures()))
    results.append(("RewardCalculator Test", test_reward_calculator()))
    results.append(("SupervisorAgent Integration Test", test_supervisor_integration()))

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:8} {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)

    print(f"\nTotal: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n🎉 All tests passed! The reward system is ready to use.")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
