from __future__ import annotations
import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

CATEGORIES = ("safe_prune", "ready_to_merge", "blocked", "orphaned")
DATE_FORMAT = "%Y-%m-%d"
PROMPT_TEMPLATES = {
    "safe_prune": "Confirm merge status and cleanup readiness. Do not delete anything automatically.",
    "ready_to_merge": "Run finishing checks, confirm merge target, and prepare a merge-or-keep recommendation.",
    "blocked": "Identify the blocker and propose the smallest next unblock step.",
    "orphaned": "Re-classify the branch/worktree from current git state plus recent session clues.",
}
FRONTMATTER_KEYS = (
    "skill", "date_scope", "scan_scope", "generated_at", "repo_count", "worktree_count",
    "branch_count", "safe_prune_count", "ready_to_merge_count", "blocked_count",
    "orphaned_count", "status", "source_sessions_dir",
)
CODEX_HOME = Path(__file__).resolve().parents[3]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan Codex sessions and git worktrees for closeout status.")
    parser.add_argument("--date", required=True, help="Local date in YYYY-MM-DD format")
    parser.add_argument("--scope", choices=("repo", "all"), required=True)
    parser.add_argument("--repo", help="Absolute repo path when scope=repo")
    parser.add_argument("--output", help="Optional output markdown path")
    args = parser.parse_args()
    try:
        datetime.strptime(args.date, DATE_FORMAT)
    except ValueError as exc:
        raise SystemExit("--date must be in YYYY-MM-DD format") from exc
    if args.scope == "repo" and not args.repo:
        raise SystemExit("--repo is required when --scope=repo")
    if args.scope == "all" and args.repo:
        raise SystemExit("--repo is only valid when --scope=repo")
    return args

def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)

def git_text(cwd: Path, *args: str) -> str:
    completed = run_command(["git", "-C", str(cwd), *args])
    return completed.stdout.strip() if completed.returncode == 0 else ""
def is_git_repo(path: Path) -> bool:
    return bool(git_text(path, "rev-parse", "--show-toplevel"))

def path_key(path: Path) -> str:
    return str(path.resolve(strict=False)).replace("\\", "/").casefold()

def session_dir_for_date(date_text: str) -> Path:
    year, month, day = date_text.split("-")
    return Path.home() / ".codex" / "sessions" / year / month / day

def resolve_repo_root(cwd: Path) -> Path:
    return Path(git_text(cwd, "rev-parse", "--show-toplevel") or cwd)

def load_session_meta(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") == "session_meta":
                    break
            else:
                return None
    except OSError:
        return None
    payload = record.get("payload") or {}
    cwd_text = payload.get("cwd")
    if record.get("type") != "session_meta" or not cwd_text:
        return None
    cwd = Path(cwd_text)
    repo = resolve_repo_root(cwd)
    return {"cwd": cwd, "repo": repo, "branch": (payload.get("git") or {}).get("branch"), "is_git": is_git_repo(repo)}

def repo_groups_for_date(date_text: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    base = session_dir_for_date(date_text)
    if not base.exists():
        return grouped
    for path in sorted(base.glob("rollout-*.jsonl")):
        meta = load_session_meta(path)
        if meta:
            grouped.setdefault(path_key(meta["repo"]), {"repo": meta["repo"], "sessions": [], "is_git": meta["is_git"]})["sessions"].append(meta)
    return grouped

def selected_repo_groups(args: argparse.Namespace, grouped: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if args.scope == "all":
        return [grouped[key] for key in sorted(grouped) if grouped[key]["is_git"]]
    repo = resolve_repo_root(Path(args.repo))
    group = grouped.get(path_key(repo), {"repo": repo, "sessions": [], "is_git": is_git_repo(repo)})
    return [group] if group["is_git"] else []

def collect_worktrees(repo: Path) -> list[dict[str, Any]]:
    text = git_text(repo, "worktree", "list", "--porcelain")
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw_line in [*text.splitlines(), ""]:
        line = raw_line.strip()
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["worktree"] = Path(line.removeprefix("worktree "))
        elif line.startswith("branch refs/heads/"):
            current["branch"] = line.removeprefix("branch refs/heads/")
        elif line.startswith("branch "):
            current["branch"] = line.rsplit("/", 1)[-1]
    return entries

def detect_base_ref(repo: Path) -> str:
    for ref_name in ("refs/remotes/origin/HEAD", "refs/remotes/upstream/HEAD"):
        output = git_text(repo, "symbolic-ref", "--quiet", "--short", ref_name)
        if output:
            return output
    branches = set(git_text(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines())
    for candidate in ("main", "master", "develop"):
        if candidate in branches:
            return candidate
    return git_text(repo, "branch", "--show-current")

def worktree_clean(worktree: Path) -> bool | None:
    status_text = git_text(worktree, "status", "--porcelain")
    return None if not status_text and not git_text(worktree, "rev-parse", "--show-toplevel") else status_text == ""

def ahead_behind(repo: Path, base_ref: str, branch: str | None) -> tuple[int | None, int | None]:
    if not base_ref or not branch:
        return None, None
    parts = git_text(repo, "rev-list", "--left-right", "--count", f"{base_ref}...{branch}").split()
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[1]), int(parts[0])
    except ValueError:
        return None, None

def branch_merged(repo: Path, base_ref: str, branch: str | None) -> bool | None:
    if not base_ref or not branch:
        return None
    code = run_command(["git", "-C", str(repo), "merge-base", "--is-ancestor", branch, base_ref]).returncode
    return True if code == 0 else False if code == 1 else None

def matching_sessions(sessions: list[dict[str, Any]], worktree: Path, branch: str | None) -> list[dict[str, Any]]:
    worktree_id = path_key(worktree)
    return [meta for meta in sessions if path_key(meta["cwd"]) == worktree_id or (branch and meta.get("branch") == branch)]

def classify_item(item: dict[str, Any]) -> str:
    if not item["is_git"] or not item["branch"]:
        return "orphaned"
    if item["branch"] == item["base_branch"]:
        return "blocked" if item["is_clean"] is False else "orphaned"
    if item["merged"] is True and item["is_clean"] is True:
        return "safe_prune"
    if item["is_clean"] is False or (item["behind"] or 0) > 0:
        return "blocked"
    if item["merged"] is False and item["is_clean"] is True and (item["ahead"] or 0) > 0 and item["has_recent_session"]:
        return "ready_to_merge"
    if item["has_recent_session"] and item["merged"] is False and (item["ahead"] or 0) == 0:
        return "blocked"
    return "orphaned"

def item_notes(item: dict[str, Any]) -> str:
    notes = ["git-fallback" if not item["is_git"] else f"base={item['base_ref']}" if item["base_ref"] else "base=unknown"]
    if item["merged"] is True:
        notes.append("merged")
    elif item["merged"] is False:
        notes.append("not-merged")
    if item["ahead"] is not None and item["behind"] is not None:
        notes.append(f"ahead={item['ahead']} behind={item['behind']}")
    notes.append("clean" if item["is_clean"] is True else "dirty" if item["is_clean"] is False else "cleanliness=unknown")
    if item["session_count"]:
        notes.append(f"sessions={item['session_count']}")
    return ", ".join(notes)

def build_item(repo: Path, entry: dict[str, Any], sessions: list[dict[str, Any]], base_ref: str, base_branch: str, is_git: bool) -> dict[str, Any]:
    worktree = Path(entry["worktree"])
    branch = entry.get("branch")
    matched = matching_sessions(sessions, worktree, branch)
    ahead, behind = ahead_behind(repo, base_ref, branch) if is_git else (None, None)
    item = {
        "repo": repo, "worktree": worktree, "branch": branch, "base_ref": base_ref, "base_branch": base_branch,
        "merged": branch_merged(repo, base_ref, branch) if is_git else None, "ahead": ahead, "behind": behind,
        "is_clean": worktree_clean(worktree), "session_count": len(matched), "has_recent_session": bool(matched), "is_git": is_git,
    }
    item["classification"] = classify_item(item)
    item["notes"] = item_notes(item)
    return item

def build_items(repo: Path, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    is_git = bool(git_text(repo, "rev-parse", "--show-toplevel"))
    base_ref = detect_base_ref(repo) if is_git else ""
    entries = collect_worktrees(repo) if is_git else []
    if not entries:
        entries = [{"worktree": repo, "branch": sessions[-1]["branch"] if sessions else None}]
    base_branch = base_ref.rsplit("/", 1)[-1] if base_ref else ""
    items = [build_item(repo, entry, sessions, base_ref, base_branch, is_git) for entry in entries]
    return sorted(items, key=lambda item: (CATEGORIES.index(item["classification"]), item["branch"] or "", str(item["worktree"])))

def slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip(".-") or "repo"

def default_output_path(date_text: str, scope_slug: str) -> Path:
    return CODEX_HOME / ".codex" / "closeout" / date_text / f"{scope_slug}-worktree-closeout.md"

def yaml_scalar(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

def build_summary(date_text: str, scope: str, repo_reports: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["classification"] for report in repo_reports for item in report["items"])
    branches = {f"{path_key(report['repo'])}:{item['branch']}" for report in repo_reports for item in report["items"] if item["branch"]}
    return {
        "skill": "worktree-closeout", "date_scope": date_text, "scan_scope": scope,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "repo_count": len(repo_reports),
        "worktree_count": sum(len(report["items"]) for report in repo_reports), "branch_count": len(branches),
        "safe_prune_count": counts.get("safe_prune", 0), "ready_to_merge_count": counts.get("ready_to_merge", 0),
        "blocked_count": counts.get("blocked", 0), "orphaned_count": counts.get("orphaned", 0),
        "status": "needs-closeout" if repo_reports else "empty-scan", "source_sessions_dir": str(session_dir_for_date(date_text)),
    }

def render_frontmatter(summary: dict[str, Any]) -> list[str]:
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        value = summary[key]
        lines.append(f"{key}: {value}" if isinstance(value, int) else f"{key}: {yaml_scalar(str(value))}")
    return [*lines, "---", ""]

def render_repo_sections(repo_reports: list[dict[str, Any]]) -> list[str]:
    lines = ["## 按 Repo 分类结果", ""]
    for report in repo_reports:
        lines.extend([f"### Repo: `{report['repo']}`", f"- 会话数: {len(report['sessions'])}"])
        for category in CATEGORIES:
            items = [item for item in report["items"] if item["classification"] == category]
            lines.append(f"#### {category}")
            if not items:
                lines.append("- NONE")
                continue
            for item in items:
                label = item["branch"] or item["worktree"].name
                lines.extend([f"- `{label}` @ `{item['worktree']}`", f"  - {item['notes']}"])
        lines.append("")
    return lines

def render_item_prompts(repo_reports: list[dict[str, Any]]) -> list[str]:
    lines = ["## 建议子 Prompt", ""]
    for report in repo_reports:
        for item in report["items"]:
            label = item["branch"] or item["worktree"].name
            lines.extend([f"- `{item['classification']}` :: `{report['repo']}` :: `{label}`", f"  - {PROMPT_TEMPLATES[item['classification']]}"])
    return lines

def render_markdown(summary: dict[str, Any], repo_reports: list[dict[str, Any]]) -> str:
    lines = render_frontmatter(summary) + [
        "# Worktree Closeout", "", "## 总览", f"- 日期：`{summary['date_scope']}`", f"- 范围：`{summary['scan_scope']}`",
        f"- Repo 数：{summary['repo_count']}", f"- Worktree 数：{summary['worktree_count']}", f"- Branch 数：{summary['branch_count']}",
        f"- safe_prune：{summary['safe_prune_count']}", f"- ready_to_merge：{summary['ready_to_merge_count']}",
        f"- blocked：{summary['blocked_count']}", f"- orphaned：{summary['orphaned_count']}", "",
        "## 建议收口顺序", "- Phase 1: 可并行 -> safe_prune", "- Phase 2: 条件并行 -> ready_to_merge",
        "- Phase 3: 串行收尾 -> blocked, orphaned", "",
    ]
    lines.extend(render_repo_sections(repo_reports))
    lines.extend([
        "## 建议总控 Prompt", "```text",
        f"Read the worktree closeout artifact for {summary['date_scope']} ({summary['scan_scope']}).",
        "Process items in this order: safe_prune -> ready_to_merge -> blocked -> orphaned.",
        "Keep risky actions manual: do not auto-merge, auto-delete, or auto-push.", "```", "",
    ])
    lines.extend(render_item_prompts(repo_reports))
    return "\n".join(lines) + "\n"

def write_artifact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def main() -> int:
    args = parse_args()
    groups = selected_repo_groups(args, repo_groups_for_date(args.date))
    repo_reports = [{"repo": group["repo"], "sessions": group["sessions"], "items": build_items(group["repo"], group["sessions"])} for group in groups]
    summary = build_summary(args.date, args.scope, repo_reports)
    scope_slug = "all-repos" if args.scope == "all" else slugify(repo_reports[0]["repo"].name if repo_reports else Path(args.repo).name)
    output_path = Path(args.output) if args.output else default_output_path(args.date, scope_slug)
    write_artifact(output_path, render_markdown(summary, repo_reports))
    print(f"Wrote closeout artifact: {output_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

