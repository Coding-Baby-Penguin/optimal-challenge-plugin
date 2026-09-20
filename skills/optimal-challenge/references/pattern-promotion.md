# Pattern Promotion

Normal execution records only tiny experience deltas. Promotion runs only after meaningful recurrence.

## Candidate signals
Repeated correction, repeated failure, repeated manual workaround, repeated unnecessary tool/agent use, repeated context/cost anomaly, stable new preference, or a platform/model capability change.

## Correct destination
| Pattern | Destination |
|---|---|
| Stable user/project preference | Preference overlay |
| Stable repo convention/fact | Repo/project instructions |
| Judgment-heavy repeatable workflow | Skill |
| Deterministic recurring enforcement | Hook/script |
| Heavy explanatory material | Reference |
| External service interaction | Plugin/MCP/connector |
| Temporary condition | State |
| One-off event | Nothing |

Do not promote from one occurrence. Repetition is evidence, not an automatic threshold.

## Hook gate
A hook is earned only when behavior is deterministic, recurrent, cheap enough per trigger, and materially valuable. Do not use hooks for architecture judgment, research-depth decisions, or other model reasoning. Account for hook trigger frequency and false-positive/latency cost.

## Lifecycle
Observe -> candidate -> test -> shadow/canary where possible -> promote or discard -> monitor -> refine, merge, split, prune, or retire.
