# Framework Selection Decision Memo

## Chosen Framework: Custom Implementation with Google Gemini

### Decision

After evaluating available agent frameworks, I chose to implement a **custom multi-agent architecture** using Google's Gemini AI API rather than adopting a pre-built framework like Simular's Agent S or Google's Agent Development Kit (ADK).

### Rationale

**1. Direct Control Over Agent Orchestration**

The mobile QA task requires precise coordination between three distinct agents (Supervisor, Planner, Executor) with specialized roles. A custom implementation provides:
- Full control over agent communication patterns
- Ability to implement domain-specific prompt engineering for each agent role
- Flexibility to optimize the supervisor's verdict logic (distinguishing FAIL_ACTION vs FAIL_ASSERTION)

**2. Simplicity and Maintainability**

Pre-built frameworks introduce abstraction layers that may not align with our specific use case:
- Agent S is optimized for general-purpose autonomous agents with memory and long-term planning
- Google ADK focuses on production-scale agent deployment with complex state management
- Our task requires a focused pipeline: Plan → Execute → Supervise, which is straightforward to implement directly

**3. LLM Model Flexibility**

Using Google Gemini's API directly allows:
- Easy model swapping (Flash, Pro, experimental versions)
- Direct access to multimodal capabilities (screenshot analysis)
- Structured output generation for action planning
- Cost optimization by choosing appropriate models for each agent role

**4. Integration with Android Tooling**

Mobile QA requires tight integration with ADB and Android UI automation:
- Custom implementation allows seamless integration of ADB commands as tool primitives
- Direct control over screenshot capture and UI XML parsing
- Ability to implement mobile-specific recovery logic (popup handling, app resets)

**5. Debugging and Transparency**

A custom architecture provides:
- Complete visibility into each agent's decision-making process
- Detailed artifact saving at each step for post-mortem analysis
- Easier debugging when tests fail or agents get stuck
- No black-box framework behaviors to troubleshoot

### Technical Implementation

The implementation uses:
- **Google Gemini API** (`google-genai` SDK) for LLM inference
- **Structured JSON output** for action planning
- **Multimodal prompting** (text + screenshots) for UI understanding
- **ADB command-line tools** for device automation
- **XML parsing** for UI hierarchy analysis

### Trade-offs

**Advantages:**
- Lightweight, minimal dependencies
- Full control over agent behavior
- Easy to extend and customize
- Model-agnostic design (can swap to other LLM providers)

**Limitations:**
- No built-in memory or state persistence across test runs
- Manual implementation of retry logic and error handling
- Limited scalability compared to production frameworks

### Conclusion

For the specific requirements of mobile QA automation, a custom implementation provides the right balance of simplicity, control, and flexibility. The straightforward supervisor-planner-executor pattern doesn't require the complexity of full-featured agent frameworks, while direct Gemini API access ensures optimal performance and cost-efficiency for the task.
