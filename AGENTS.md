<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

Use the `/trellis:start` command when starting a new session to:
- Initialize your developer identity
- Understand current project context
- Read relevant guidelines

Use `@/.trellis/` to learn:
- Development workflow (`workflow.md`)
- Project structure guidelines (`spec/`)
- Developer workspace (`workspace/`)

If you're using Codex, project-scoped helpers may also live in:
- `.agents/skills/` for reusable Trellis skills
- `.codex/agents/` for optional custom subagents

Keep this managed block so 'trellis update' can refresh the instructions.

<!-- TRELLIS:END -->

## Project UI Constraints

1. Development constraints: All pages, components, and layout elements must utilize 100% of shadcn/ui components (https://ui.shadcn.com/), strictly adhering to its design system and style specifications; the introduction of third-party UI libraries is prohibited, and non-essential native styles are not allowed, ensuring complete uniformity in project layout, visuals, and interactive styles.
