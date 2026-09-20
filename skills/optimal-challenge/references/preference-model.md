# Preference Model

Learn operational preferences, not sensitive personal traits or inferred identity characteristics. Keep project-local preferences local when project isolation applies.

## Evidence strength
Explicit current request > explicit correction > repeated user choice > repeated successful acceptance > assistant inference.

## Scope and decay
Store preferences as `condition -> behavior -> scope -> confidence`, not global personality labels. Prefer turn/session/project/stable scopes. Weak or old inferred preferences decay; explicit contradiction overrides immediately.

## Runtime retrieval
Load only preferences relevant to the current task. Compress established preferences into small execution-policy fields such as verbosity, delegation bias, context budget, source preference, artifact format, or display of verification evidence.

## Priority
Correctness/safety > explicit current request > project goal/constraints > explicit stable preference > established inferred preference > weak inference.

Preferences may adjust defaults but never expand permissions, weaken safeguards, change isolation boundaries, redefine goals, or override factual evidence.
