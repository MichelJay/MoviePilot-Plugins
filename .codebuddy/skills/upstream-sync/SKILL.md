---
name: subscribeassistantenhanced-sync
description: This skill synchronizes upstream changes from InfinityPacer/MoviePilot-Plugins into a cleaned fork that retains only the subscribeassistantenhanced plugin. It should be used when the user asks to sync with upstream, pull latest changes from the original repo, update plugin code from upstream, or when GitHub shows "N commits behind InfinityPacer/MoviePilot-Plugins:main". It uses a cherry-pick + merge -s ours strategy to avoid bringing back 400+ unrelated files that were removed during repo cleanup.
---

# SubscribeAssistantEnhanced 上游同步

## 概述

本 skill 用于从 `InfinityPacer/MoviePilot-Plugins` 上游仓库同步 `subscribeassistantenhanced` 插件的更新。

**核心问题**: 此仓库是上游的精简分叉（fork），只保留了 `subscribeassistantenhanced` 插件，其余 400+ 个文件已在一次大规模清理提交中删除。因此标准 `git merge`/`git pull` 不可用——它们会带回所有已删除的无关文件。

**解决方案**: 使用 `git cherry-pick` 精确选取上游对插件代码的改动，然后使用 `git merge -s ours` 标记已同步（消除 GitHub 的 "N commits behind" 提示）。

## 重要: 路径重命名

**上游仓库**: `plugins.v2/subscribeassistantenhanced/`（旧名）
**本地仓库**: `plugins.v2/SubscribeAssistantEnhancedPro/`（新名，Pro 重命名）

同步时需要关注两个路径：
- 用上游旧名 (`subscribeassistantenhanced`) 检测上游变更
- cherry-pick 后，如果改动落在旧路径下，需要**手动迁移到新路径** (`SubscribeAssistantEnhancedPro`)
- 脚本已自动处理路径引用，但迁移操作仍需人工确认

## 何时触发

当用户提出以下请求时，使用本 skill:

- "同步上游"
- "更新插件代码"
- "拉取上游最新改动"
- "fix the behind ahead issue on GitHub"
- "sync with InfinityPacer"
- GitHub 显示 "This branch is N commits behind"

## 同步流程

### 决策树

```
用户请求同步
├─ 工作区是否干净？
│   ├─ 否 → 提示用户先提交或暂存，等待确认
│   └─ 是 → 继续
├─ git fetch upstream main
├─ git log --oneline HEAD..upstream/main
│   ├─ 无输出 → 已是最新，无需同步
│   └─ 有输出 → 继续
├─ git diff --name-only HEAD..upstream/main -- plugins.v2/subscribeassistantenhanced tests
│   ├─ 无输出 → 直接 merge -s ours（无插件变更）
│   └─ 有输出 → cherry-pick + merge -s ours
└─ git push origin main（如用户要求）
```

### 快速执行（推荐优先尝试脚本）

如果有 PowerShell 可用，直接执行脚本一步完成:

```powershell
# 仅同步（不推送）
.\.codebuddy\skills\upstream-sync\scripts\sync-upstream.ps1

# 同步并推送
.\.codebuddy\skills\upstream-sync\scripts\sync-upstream.ps1 -Push
```

脚本处理所有边界情况: 工作区检查、上游远程验证、冲突检测与提示。

### 手动执行（纯 git 命令）

如果无法运行 PowerShell 脚本（如 Linux/Mac 环境，或 AI 需要精确控制每一步），按顺序执行以下命令:

```bash
# 1. 拉取上游
git fetch upstream main

# 2. 查看有哪些新提交
git log --oneline HEAD..upstream/main

# 3. 检查新提交是否涉及插件
git diff --name-only HEAD..upstream/main -- plugins.v2/subscribeassistantenhanced tests

# 4. 根据结果:
#   - 无输出: git merge -s ours upstream/main -m "sync: no plugin changes"
#   - 有输出: git cherry-pick <hash1>; git cherry-pick <hash2>; ...

# 5. 消除 GitHub "behind" 提示
git merge -s ours upstream/main -m "sync: mark upstream as merged"

# 6. 推送
git push origin main
```

详细的纯命令参考（含冲突处理步骤）见 `references/sync-commands.md`。

## 冲突处理

当 `git cherry-pick` 失败时:

1. **识别冲突**: `git diff --name-only --diff-filter=U` 列出冲突文件
2. **判断类型**: 
   - 普通冲突（文件已有本地修改）→ 手动编辑合并
   - 稀疏检出冲突（文件提示不存在）→ 使用下方的稀疏检出方案
3. **编辑合并**: 在冲突文件中找到 `<<<<<<<` / `=======` / `>>>>>>>` 标记，手动保留正确内容
4. **确认干净**: 再次运行 `git diff --name-only --diff-filter=U`，确认无输出
5. **继续**: `git add <文件>` → `git cherry-pick --continue`
6. **标记同步**: `git merge -s ours upstream/main`
7. **推送**: `git push origin main`

遇到稀疏检出导致的冲突（tests 文件不在工作区），先运行:
```bash
# 注意: 路径从仓库根开始，如 /tests/test_integration.py
git sparse-checkout add /tests/<文件名>
git checkout --theirs <文件名>
git add <文件名>
git cherry-pick --continue
```

## 关键限制

| 绝对禁止 | 原因 |
|----------|------|
| `git merge upstream/main` | 带回 400+ 已删除的无关文件 |
| `git pull upstream main` | 等同 fetch + merge，同上 |
| `git rebase upstream/main` | 同上 |

**每次上游有新提交后，必须重新执行 `git merge -s ours upstream/main`**。这个标记只对执行时的 upstream HEAD 生效，不是永久性的。

## 踩坑经验

以下是多次同步过程中实际遇到的问题和解决方案:

### 坑 1: cherry-pick 后 GitHub 仍显示 "N commits behind"

**现象**: 执行了 `git cherry-pick` 拿到上游代码，推送后 GitHub 仍提示 "This branch is N commits behind"。

**原因**: `git cherry-pick` 会生成全新的 commit hash，与原上游提交 hash 不同。GitHub 对比的是 commit 是否存在于当前分支历史中，而不看代码内容。原始提交（如 `26c71f5`）从未出现在当前分支，所以 GitHub 认为你没追上。

**解决**: cherry-pick 之后必须再执行 `git merge -s ours upstream/main`。这个命令不修改任何文件，只在 commit 历史中记录一条合并标记，告诉 git "上游的这些提交已被处理"。执行顺序很重要：**先 cherry-pick 拿代码，再 merge -s ours 标记**。如果反过来先 merge -s ours，后续就无法 cherry-pick 了。

### 坑 2: merge -s ours 不是一次性的

**现象**: 上次同步后 GitHub 显示已追平，过几天上游推送新代码后又显示 "1 commit behind"。

**原因**: `merge -s ours` 只标记执行时的 upstream HEAD。上游每天早上都会推送一批新提交（自动同步脚本），每个新提交都需要重新执行 `merge -s ours`。

**解决**: 这不是 bug，而是正常现象。每次同步上游时，完整执行 cherry-pick（如果有插件改动）+ merge -s ours 即可。

### 坑 3: sparse-checkout 导致 cherry-pick 冲突

**现象**: `git cherry-pick <hash>` 报错冲突，提示 `test_integration.py`、`test_verifier.py` 等文件不存在。

**原因**: 本仓库的 sparse-checkout 只检出了部分文件。上游提交中可能修改了不在 sparse-checkout 范围内的 test 文件，git 找不到这些文件就报冲突。

**解决**: 
```bash
# 临时加入 sparse-checkout，用 theirs 策略接受上游版本
git sparse-checkout add /tests/<文件名>
git checkout --theirs <文件名>
git add <文件名>
git cherry-pick --continue
```
注意路径是 `/tests/test_verifier.py` 而不是 `/tests/v2/subscribeassistantenhanced/test_verifier.py`。

### 坑 4: cherry-pick --no-commit 可能带进无关文件

**现象**: 如果上游某个提交同时修改了插件文件和其他仓库文件（如 workflow、配置等），`git cherry-pick --no-commit` 会把所有变更都应用到暂存区，不加以区分就 commit 会引入不该有的文件。

**解决**: 执行 `git cherry-pick --no-commit <hash>` 后，先 `git status --porcelain` 查看所有已暂存的变更，确认只包含 `plugins.v2/subscribeassistantenhanced/` 和 `tests/` 下的文件。如有无关文件，用 `git reset HEAD <无关文件>` 移出暂存区，再执行 `git commit`。

### 坑 5: PowerShell 中不能用 goto

**现象**: 早期版 sync-upstream.ps1 使用了 `goto PUSH_STEP` 语法，在 PowerShell 中报错。

**原因**: PowerShell 不支持 goto 语句（那是批处理的语法）。

**解决**: 使用 `if/else` 结构替代跳转逻辑。

## 参考资源

- `references/sync-commands.md` — 纯 git 命令参考，可在任何 AI 对话中独立使用
- `scripts/sync-upstream.ps1` — PowerShell 自动化脚本

> 插件打包请使用 `plugin-package` skill。
