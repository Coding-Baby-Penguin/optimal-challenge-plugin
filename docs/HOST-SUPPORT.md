# Supported host workflow boundaries

Documentation checked 2026-10-16. This is compatibility guidance, not an account
entitlement or live acceptance report. See PROJECT-STATE.md for current verified work.

| Surface | Native path and current guidance | Proof still required |
|---|---|---|
| Codex CLI/Desktop | Installed skill discovery, exposed native tools, repository instructions; parent sandbox and approvals are inherited by subagents. GPT-6.1 Sol is `gpt-6.1-sol`; retain a known adequate active effort unless a supported override is needed and read back. | Exact installed identity, client/model/effort and effective permissions for each exercised surface. CLI success does not prove Desktop. |
| ChatGPT Work/Codex | Follow tools/skills exposed in that task; compact durable handoff if resume is unavailable. | Own installed invocation and outcomes. Do not infer from ordinary ChatGPT Chat or the CLI. |
| Claude Code | Installed plugin skills, native subagents/tools and actual login/provider route. Opus/Sonnet/Haiku 5.5 require Code 2.1.280/2.1.284/2.1.293 respectively. Per-invocation subagent effort is documented from 2.1.292. Plugin subagents ignore permissionMode, hooks and MCP-server frontmatter. | Auth, model resolution, installed discovery and effective tool restrictions. A Desktop session does not establish Code access. |
| OpenAI API / Anthropic API / SDKs | Separate explicit integration/evaluation only; this update adds no API adapter. | Executable matching adapter plus current acceptance where the legacy contract requires it. No support or billing inference from product subscriptions. |

OpenAI API Sol supports low/medium/high/xhigh/max effort; none/minimal are unsupported.
A host may advertise a different set (including ultra). Such host controls are not
portable API enum values, and a catalog is not evidence they were used. No automatic
upgrade, paid acceleration, larger context or extra concurrency is selected here.

Use host permission controls as actually implemented. Role words such as read-only
are instructions, not enforcement. Windows command-network isolation depends on the
active sandbox implementation; it does not disable model transport or every web or
connector tool. A required unavailable restriction blocks the dependent operation.

Official primary sources:

- [Codex/ChatGPT model surfaces](https://learn.chatgpt.com/docs/models)
- [Codex subagents and inheritance](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex skill discovery](https://learn.chatgpt.com/docs/build-skills)
- [Codex approvals](https://learn.chatgpt.com/docs/agent-approvals-security)
- [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- [GPT-6.1 Sol API](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Claude Code model configuration](https://code.claude.com/docs/en/model-config)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code skills](https://code.claude.com/docs/en/skills)

Native operation does not require the optional legacy Python controller. Its static
policy-only matrix and fail-closed tests remain intact for that explicitly selected
mode. Documented, advertised, used, denied, unknown and blocked stay distinct.
