# README Maintenance

Load this module when creating a repository, changing installation or usage, moving files, adding configuration, changing commands, or preparing a release.

## Reader contract

The README is the front door, not the complete manual. It lets a new reader answer: what does this project do, why is it useful, how do I start, how do I configure and use it, how do I validate changes, where is current project state, and where can I get help?

Use `templates/README-TEMPLATE.md` as a selectable structure. Remove irrelevant sections instead of leaving empty placeholders.

## Clean style

- Use one H1 containing the project name.
- Use sentence case, descriptive headings, and a logical hierarchy without skipped levels.
- Lead with a one-paragraph purpose and value statement; put the shortest working quick start before architectural detail.
- Prefer short paragraphs, focused lists, and one verified example per common path.
- Use relative links for repository files and meaningful link text.
- Keep commands copyable and mark placeholders clearly; never include real secrets or machine-specific paths.
- Link to detailed documents instead of duplicating material that will drift.

## Maintenance rule

Update the README in the same change that alters public behavior, prerequisites, configuration, paths, commands, packaging, deployment, support, or state-file location. Verify commands from a clean-enough environment, check relative links and referenced paths, compare named versions with manifests/configuration, and remove stale instructions rather than layering exceptions over them.

Before completion, read the README in user order: purpose, quick start, configuration, usage, development, support. Confirm that a first-time reader does not need chat history to succeed.
