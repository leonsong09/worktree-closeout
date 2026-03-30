# closeout

A read-only skill for triaging branch and worktree closeout status across sessions.

## What this skill does

`closeout` helps an agent:
- resolve a scan date,
- decide whether to scan the current repo or all repos involved,
- run a closeout scanner,
- read the generated artifact,
- summarize the safe handling order,
- output controller and per-item prompts for follow-up.

It is intentionally **read-only** and does not grant permission to merge, delete, prune, or push.

## When to use

Use this skill when the user says things like:
- “worktree closeout”
- “branch closeout”
- “parallel closeout”
- “工作树收口”
- “分支收口”
- “并行收口”

## When not to use

This skill is **not** the best fit when the user wants:
- only the current session summary,
- only a same-day project report,
- immediate branch merge/delete execution,
- a generic git cleanup without date-based evidence.

## Trigger phrases

English:
- worktree closeout
- branch closeout
- parallel closeout

Chinese:
- 工作树收口
- 分支收口
- 并行收口

## Workflow

1. **Resolve the date first**
   - Convert relative expressions into an exact date.

2. **Resolve the scope second**
   - Current repo or all repos.

3. **Run the scanner**
   - Use the included script from the skill root or adapt the path to your local install.

4. **Read the artifact**
   - Treat the generated artifact as the source of truth for status classification.

5. **Summarize the closeout order**
   - Present safe parallel and serial phases clearly.

6. **Output follow-up prompts**
   - Provide a controller prompt and per-item prompts without performing destructive actions.

## Installation

Copy the folder into your local skills directory.

Common locations:

- Codex: `~/.codex/skills/closeout`
- Agents-style setups: `~/.agents/skills/closeout`

## Repository structure

```text
closeout/
  SKILL.md
  README.md
  LICENSE
  .gitignore
  agents/
  references/
  scripts/
```

## Configuration

The included scanner script is part of the public bundle.

Recommended command pattern from the skill root:

```bash
python -X utf8 ./scripts/scan_closeout.py --date <YYYY-MM-DD> --scope <repo|all> [--repo <ABSOLUTE_REPO_PATH>]
```

## Usage example

### Example prompt

```text
工作树收口
```

### Expected behavior

The agent should:
- resolve the exact date,
- ask for the scan scope,
- run the scanner in read-only mode,
- summarize the artifact,
- provide prompt-ready follow-up instructions,
- avoid merge/delete/prune/push side effects.

## Output example

```markdown
## 收口概览
- 日期：2026-03-30
- 范围：all
- 优先处理：repo-a / repo-b

## 建议顺序
- Phase 1: safe_prune
- Phase 2: ready_to_merge
- Phase 3: blocked / orphaned
```

## Limitations

- This skill depends on the bundled scanner and artifact format.
- It is a triage workflow, not an execution workflow.
- It should not be used as permission for destructive git actions.

## License

MIT
