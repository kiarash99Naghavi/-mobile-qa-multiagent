# Framework Selection Decision

## Why Custom Implementation with Google Gemini

After evaluating several existing agent frameworks (Simular's Agent S, Google ADK, LangChain Agents), I decided to build a custom multi-agent architecture using Google's Gemini AI API directly.

### Reasoning

**1. Better Control Over Agent Orchestration**

The mobile QA testing workflow requires tight coordination between three specialized agents with very specific roles. Building this from scratch gave me:
- Complete control over how agents communicate and hand off work
- Ability to tune prompts specifically for each agent's responsibility
- Flexibility to implement nuanced logic, like the Supervisor's ability to distinguish between FAIL_ACTION and FAIL_ASSERTION

**2. Simplicity Over Abstraction**

Most frameworks are built for more general use cases:
- Agent S is designed for autonomous agents with memory and long-term planning capabilities
- Google ADK targets production deployments with complex state management needs
- My use case is simpler: Plan → Execute → Supervise. This linear pipeline doesn't need heavy abstractions

**3. Direct Access to Gemini's Capabilities**

Working directly with the Gemini API provided several advantages:
- Easy to swap between models (Flash for speed, Pro for complex reasoning)
- Straightforward multimodal prompting (feeding screenshots to the LLM)
- Native structured output for action planning
- Better cost control by selecting different models for different agents

**4. Cleaner Android Integration**

Mobile testing needs deep integration with Android tooling:
- I could build ADB commands directly into the action primitives
- Screenshot capture and UI XML parsing happen exactly when needed
- Mobile-specific behaviors (popup handling, app state resets) are first-class features rather than workarounds

**5. Easier Debugging**

Without framework abstractions, debugging is more straightforward:
- Full visibility into what each agent is thinking and doing
- Artifacts saved at every step (screenshots, actions, verdicts)
- When something fails, I know exactly where to look
- No mysterious framework behaviors to reverse-engineer

### Technical Stack

The implementation consists of:
- **Google Gemini API** via the `google-genai` SDK for LLM inference
- **Structured JSON outputs** for action specifications
- **Multimodal prompts** combining text instructions with screenshots
- **ADB CLI** for Android device control
- **XML parsing** for UI hierarchy analysis

### Trade-offs

**Benefits:**
- Minimal dependencies and lightweight codebase
- Complete control over all agent behaviors
- Straightforward to extend and modify
- Not locked into any specific LLM provider

**Limitations:**
- No built-in memory across test runs (each test starts fresh)
- Had to implement retry and error handling manually
- Won't scale to massive parallel test execution without additional work

### Summary

For this mobile QA automation project, building a custom solution made more sense than adopting a general-purpose agent framework. The supervisor-planner-executor pattern is simple enough that framework overhead would add complexity without clear benefits. Direct API access to Gemini provides the multimodal capabilities I need while keeping the implementation clean and maintainable.
