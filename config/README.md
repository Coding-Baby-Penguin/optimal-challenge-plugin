# Project configuration

This folder is the canonical home for project-owned, shareable configuration. `project.json` supplies maintenance metadata used by validation and packaging workflows so names, versions, paths, and commands are not repeated in scripts.

Tool-required manifests remain at the repository root or their mandated discovery paths. Validation checks them against `project.json` to catch drift.

## Precedence

1. Stable code defaults and platform requirements.
2. Committed configuration in this folder.
3. Ignored local environment overrides.
4. Runtime secret injection from environment variables or an approved secrets manager.

Never store passwords, tokens, private keys, or live credentials here. Commit only sanitized examples and document the type, purpose, default, and allowed values of every setting.

## Deliberately retained literals

- Plugin manifests repeat the name, version, repository, schema, and skills path because their platforms require self-contained metadata; validation compares each copy with `project.json`.
- Publisher, policy, and support URLs remain in manifests and user documents where they are public metadata rather than deploy-varying configuration.
- Fake paths and placeholders in documentation remain local to their examples and must never contain machine-specific or secret values.
- Release-history text under `submission/` records the release it describes and is not runtime configuration.
