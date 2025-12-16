# Framework Selection Decision

## Why Custom Implementation with Google Gemini

After evaluating existing agent frameworks (Simular's Agent S, Google ADK, LangChain Agents), I built a custom multi-agent architecture using Google's Gemini AI API directly.

### Key Reasoning

**1. Future-Proof for Fast LLMs and SLMs**

A major driver for the custom implementation was flexibility to integrate fast vision-language models:
- Easy migration to [Apple's Fast Vision-Language Models](https://machinelearning.apple.com/research/fast-vision-language-models) for iOS testing
- Compatible with emerging SLMs (Small Language Models) for near-real-time testing
- Framework-agnostic design allows rapid experimentation with lightweight models
- Enables on-device testing without cloud API dependencies

**2. Better Control Over Agent Orchestration**

The mobile QA workflow requires tight coordination between three specialized agents:
- Complete control over agent communication and handoffs
- Custom prompt tuning for each agent's specific role
- Nuanced logic implementation (e.g., Supervisor distinguishing FAIL_ACTION vs FAIL_ASSERTION)

**3. Simplicity Over Abstraction**

My use case is a linear pipeline: Plan → Execute → Supervise
- Most frameworks target complex scenarios with memory and long-term planning
- Direct implementation avoids unnecessary abstraction layers
- Cleaner codebase that's easier to understand and modify

**4. Direct Gemini API Benefits**
- Easy model switching (Flash for speed, Pro for reasoning)
- Native multimodal prompting (screenshots + text)
- Structured JSON outputs
- Better cost control per agent

**5. Mobile-First Integration**
- ADB commands built directly into action primitives
- Screenshot capture and UI XML parsing exactly when needed
- Mobile-specific behaviors as first-class features

### Technical Stack
- Google Gemini API via `google-genai` SDK
- Structured JSON outputs for actions
- Multimodal prompts (text + screenshots)
- ADB CLI for Android control
- XML parsing for UI hierarchy

### Trade-offs

**Benefits:**
- Minimal dependencies, lightweight codebase
- Not locked into any LLM provider
- Ready for SLM integration and real-time testing
- Complete control over agent behaviors

**Limitations:**
- No built-in memory across test runs
- Manual retry/error handling implementation
- Additional work needed for massive parallel execution

### Summary

Building a custom solution provided the flexibility needed for future SLM integration while keeping the implementation clean and maintainable. The architecture is designed to easily swap in faster vision-language models for real-time mobile testing scenarios.
