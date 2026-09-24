# Folder Architecture

Load this module when creating a project or subsystem, adding a new artifact category, reorganizing files, or when project root clutter obscures ownership.

## Principle

Use the ecosystem's official conventions before generic preferences. Folder structure is an interface consumed by compilers, import systems, test discovery, packaging, CI, deployment, contributors, and automation. A good layout makes responsibility and lifecycle obvious without adding empty abstraction.

## Planning workflow

1. Inventory the current tree, manifests, source/import roots, test runners, packaging and deployment globs, CI commands, ignore rules, and repository instructions.
2. Identify the project type and ecosystem conventions. Do not force one universal layout: Python packages, Rust crates, Go modules, web applications, plugins, monorepos, and static sites have different discovery rules.
3. Classify each artifact as project metadata, configuration, source, tests, validation, fixtures/test data, scripts/tooling, documentation, generated output, distributable output, or private/local state.
4. Produce `templates/FOLDER-PLAN.md` before a non-trivial restructure. Show the current tree, proposed tree, placement rules, migration map, path consumers, verification, and rollback.
5. Resolve material choices with the user before moving files. For a new project, create the approved folders and `.gitignore` before generating their contents.

## Placement rules

- Keep the project root for entry documentation, licenses, ecosystem manifests/locks, required tool configuration, and intentionally root-discovered entry points.
- Put project-owned, shareable configuration and schemas in `config/`. Preserve tool-required root files and secrets-management boundaries.
- Put product source where the ecosystem expects it. Prefer a Python `src/` package layout when packaging/import isolation matters; retain simple Go package files at module root when that is the native convention; use Cargo's standard `src/`, `tests/`, `examples/`, and `benches/` discovery paths.
- Put integration, end-to-end, package-validation, and other repository-level tests outside product source unless the ecosystem deliberately colocates them. Give a distinct validation test suite its own `tests/validation/` folder.
- Separate unit, integration, end-to-end, validation, fixtures, and helpers only when they have different scope, dependencies, run cadence, security boundary, or enough files to improve navigation.
- Put reusable developer/operator automation in `scripts/` or the ecosystem-standard equivalent. Keep generated and distributable artifacts separate from authored source and ignore them unless publication requires tracking.
- Do not create a one-file folder merely for symmetry. A one-file folder is justified by tool discovery, a distinct lifecycle or boundary, or near-term files already required by the approved work.
- Mirror source subtrees in tests only when it improves discovery; prefer feature/domain ownership when the codebase already uses it consistently.

## Migration safety

Treat every file move as an interface change. Search and update all path consumers: imports and references, manifests, build/package configuration, test discovery, CI workflows, scripts, documentation commands, deployment rules, and `.gitignore` patterns. Preserve unrelated user changes and use version-control-aware moves where practical.

Verify the new layout with path searches, test collection, the full suite, build/package checks, and a clean artifact/secret audit. If a consumer cannot be updated safely, follow the folder plan's rollback and leave the old layout intact.

## Evidence basis

The adaptable approach follows official guidance: Python packaging distinguishes `src` and flat layouts; pytest supports separate or colocated tests; Cargo assigns conventional discovery folders; and Go keeps simple modules flat while adding packages and `internal/` as complexity grows.
