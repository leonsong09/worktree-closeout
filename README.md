# worktree-closeout

[![License](https://img.shields.io/github/license/leonsong09/worktree-closeout)](https://github.com/leonsong09/worktree-closeout/blob/main/LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/leonsong09/worktree-closeout)](https://github.com/leonsong09/worktree-closeout/commits/main)
[![Repo Size](https://img.shields.io/github/repo-size/leonsong09/worktree-closeout)](https://github.com/leonsong09/worktree-closeout)

> 面向多 session / 多 worktree / 多分支场景的**只读收口盘点 skill**，用于扫描状态、输出优先级与 follow-up prompts，而不是直接做危险 git 操作。

## 适用场景

当用户想要：
- worktree closeout
- branch closeout
- parallel closeout
- 工作树收口
- 分支收口
- 并行收口
- 需要按日期扫描哪些分支/worktree 还没收口

## 不适用场景

以下情况更适合其他 skill：
- 当前单次会话总结：`session-wrap`
- 同日按项目日报：`project-daily-summary`
- 单分支已经选定并准备正式 finish：`finishing-a-development-branch`

## 触发词

中文：
- 工作树收口
- 分支收口
- 并行收口

English:
- worktree closeout
- branch closeout
- parallel closeout

## 工作流

1. 先解析并复述**确切日期**。
2. 再确认扫描范围：当前 repo / 所有 repo。
3. 运行内置扫描脚本，生成 closeout artifact。
4. 读取 artifact，并按分类输出优先收口顺序。
5. 输出 controller prompt 与 per-item prompt。
6. 整个流程保持只读：不自动 merge、delete、prune、push。

## 安装

将整个目录复制到本地技能目录，例如：

```text
~/.codex/skills/worktree-closeout
```

或：

```text
~/.agents/skills/worktree-closeout
```

## 仓库结构

```text
worktree-closeout/
  SKILL.md
  README.md
  LICENSE
  .gitignore
  agents/
  references/
  scripts/
```

## 配置

推荐从技能根目录运行：

```bash
python -X utf8 ./scripts/scan_closeout.py --date <YYYY-MM-DD> --scope <repo|all> [--repo <ABSOLUTE_REPO_PATH>]
```

## 用法示例

### 示例输入

```text
工作树收口
```

### 预期行为

- 先解析日期
- 再问扫描范围
- 只读运行扫描器
- 汇总 artifact
- 生成建议顺序与 prompts
- 不执行危险 git 操作

## 输出示例

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

## 限制

- 这是 triage / orchestration 辅助 skill，不是执行型 skill。
- 依赖内置脚本与 artifact 格式。
- 不应被当作 merge / delete / prune 的授权。

## License

MIT
