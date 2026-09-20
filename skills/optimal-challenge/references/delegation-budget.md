# Delegation Budget

The parent is process authority. Workers execute narrow roles.

## Break-even gate
Delegate only when isolation, independent judgment, parallelism, or context containment is worth fresh-context and coordination cost. Keep trivial, tightly coupled, and single-file mechanical work inline. Batch small same-shape edits.

## Capability lease
Every worker receives:
- one outcome and done condition;
- minimum required context/files;
- allowed skills/tools;
- conditional capabilities with observable triggers;
- forbidden orchestration/planning skills;
- no-subagent rule unless explicitly authorized;
- escalation return contract;
- compact output schema.

Workers do not independently re-run project brainstorming/planning. If a missing capability is material, return `NEEDS_CAPABILITY` with reason and impact; the parent decides whether to grant it.

## Review depth
- Low risk: implement + direct verification.
- Medium risk: implement + one independent/fresh review when useful.
- High risk: task-level and/or integration review proportional to consequence.

## Delta output
Prefer status, changed artifacts, evidence, decisions, concerns, and requested escalation. Store verbose reports as files when needed instead of returning them into parent context.

## Stop-loss
Stop/reframe a strategy when the same failure/hypothesis repeats, files are reread without new evidence, context grows without state progress, or review/fix loops cycle. Checkpoint evidence, identify the missing fact, then choose a targeted capability, stronger context/model, fresh pass, or user escalation.
