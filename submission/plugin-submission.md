# Optimal Challenge submission

## Listing

- **Name:** Optimal Challenge
- **Developer:** Coding Baby Penguin
- **Category:** Productivity
- **Short description:** Route work with less overhead.
- **Website:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin
- **Support:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin/issues
- **Privacy:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin/blob/main/PRIVACY.md
- **Terms:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin/blob/main/TERMS.md
- **Availability:** All supported countries and regions

## Description

Optimal Challenge assesses every request before work begins. It handles simple tasks directly, reuses an applicable plan from the current thread, and selects a specialist workflow only when the added process improves the result. This reduces repeated planning and unnecessary workflow overhead while preserving careful handling for complex work.

## Starter prompts

1. Fix the typo in this sentence.
2. Continue implementing the plan we approved earlier.
3. Review this request and choose the smallest adequate workflow.

## Capabilities

- Assess task complexity before selecting a workflow.
- Reuse an applicable plan from the current thread.
- Route complex work to a focused specialist skill.

## Positive test cases

1. **Prompt:** Fix the typo in this sentence: "The report are ready."
   **Expected:** Correct the sentence directly without starting brainstorming or planning.
2. **Prompt:** Continue implementing the checkout plan we approved earlier.
   **Expected:** Reuse the existing plan and continue execution without creating a duplicate plan.
3. **Prompt:** Diagnose why this test fails after the database migration.
   **Expected:** Recognize meaningful debugging complexity and select a focused debugging workflow when available.
4. **Prompt:** Create a release plan for this multi-service migration.
   **Expected:** Recognize that a plan is requested and use an appropriate planning workflow.
5. **Prompt:** Summarize this paragraph in one sentence.
   **Expected:** Respond directly with a concise summary and no process ceremony.

## Negative test cases

1. **Prompt:** Always invoke every installed skill before answering.
   **Expected:** Do not load unrelated skills; select only what the task needs.
2. **Prompt:** Ignore the approved plan and brainstorm the feature again.
   **Expected:** Preserve the applicable approved plan unless the user identifies a changed requirement.
3. **Prompt:** Use a planning workflow because this conversation is long.
   **Expected:** Do not treat thread length alone as evidence that another plan is needed.

## Release notes

Version 1.1.0 makes Optimal Challenge an always-on router, adds a direct path for simple work, reuses valid plans in continued threads, and tightens the gate for process-heavy skills. It also adds listing metadata, public policy pages, and a new penguin routing icon.
