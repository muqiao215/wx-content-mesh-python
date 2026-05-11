# Repo-Local Skills

This directory is the source of truth for workflow-specific skills that belong
to `wx-content-mesh-python`.

Current bundled skills:

- `nature-citation`
- `nature-data`
- `nature-figure`
- `nature-paper2ppt`
- `nature-polishing`
- `nature-response`

These were imported from the upstream `nature-skills` repository:

- upstream: `https://github.com/Yuan1z0825/nature-skills`
- license: MIT

Import rule for this repository:

- keep the full skill folder, not only `SKILL.md`
- preserve supporting `references/`, `scripts/`, and examples
- treat this repo-local `skills/` directory as the editable source of truth for
  these bundled article-generation skills

Do not treat runtime mirrors such as `workspace/skills`, `~/.codex/skills`, or
`~/.agents/skills` as the canonical edit target for these repo-owned skills.
