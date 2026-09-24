# Configuration Governance

Load this module when creating or reviewing application settings, repeated literals, deployment values, credentials, endpoints, paths, feature flags, provider identifiers, or project configuration.

## Hard-code audit

Before declaring implementation complete, search authored source and automation for repeated or environment-sensitive literals. Review URLs and hosts, ports, absolute paths, timeouts, retry limits, quotas, feature flags, locale/region/provider/model identifiers, account IDs, and credential-like values. Exclude generated output, vendored dependencies, documented examples, and a test fixture only after confirming its scope.

Classify every finding:

| Finding | Destination |
|---|---|
| Domain invariant that never varies independently of code | A descriptive named constant with a focused test |
| Deploy-varying, user-selectable, or operational value | Typed configuration |
| Secret or credential | Environment injection or a secret manager; never committed configuration |
| Stable test-only value | Named fixture/helper inside the test boundary |
| Documentation example | Clearly fake placeholder that cannot be mistaken for a live value |

Do not externalize every literal. Configuration without a real variation point hides behavior and increases failure modes. After refactoring, rerun the audit and document any deliberately retained values.

## Configuration layout

Use `config/` as the canonical home for project-owned, shareable configuration, schemas, example files, and configuration documentation. Keep a tool-required root manifest where its tool requires it; make that root file a thin entry point into `config/` when the tool supports indirection.

Use one single loader or access layer. Define and document precedence once, for example: code defaults, committed project configuration, local environment overrides, then runtime secret injection. Validate types and required fields at startup or the earliest deterministic boundary. Unknown keys and invalid values must fail with actionable errors rather than silently falling back.

Never put real secrets in `config/`. Commit sanitized examples such as `.env.example`; ignore local overrides and credential files from the start. Document each key's purpose, type, default, allowed values, source, and whether it is secret.

## Completion contract

A configuration change is complete when code uses the central access layer, duplicated literals are removed, examples and ignore rules are safe, tests cover default/override/invalid cases, and README configuration instructions are updated in the same change.
