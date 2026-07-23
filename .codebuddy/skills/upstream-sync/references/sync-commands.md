# Upstream Sync - 纯 Git 命令参考

本文件提供可逐行复制执行的纯 git 命令，用于在没有 PowerShell 脚本的环境中完成上游同步。每个命令独立可运行。

## 前置条件

```bash
# 确认 upstream 远程已配置
git remote -v

# 如果没有 upstream，添加它
git remote add upstream https://github.com/InfinityPacer/MoviePilot-Plugins.git
```

## 标准同步流程（无冲突）

```bash
# === 阶段 1: 拉取上游 ======================================

# 1.1 拉取上游最新代码
git fetch upstream main

# 1.2 查看上游新提交
git log --oneline HEAD..upstream/main

# 1.3 检查新提交是否涉及插件文件
git diff --name-only HEAD..upstream/main -- plugins.v2/subscribeassistantenhanced tests

# === 阶段 2: 处理变更 ======================================

# 2a. 如果没有插件变更（1.3 无输出）→ 直接标记同步:
git merge -s ours upstream/main -m "sync: mark upstream as merged (no plugin changes)"

# 2b. 如果有插件变更（1.3 有输出）→ cherry-pick:
# 先列出所有待处理的提交（从旧到新）
git log --oneline --no-merges --reverse HEAD..upstream/main --format="%H"

# ⚠️ 推荐 --no-commit 方式：可在 commit 前检查文件范围
#    防止上游提交中混入非插件文件（如 workflow、配置等）
git cherry-pick --no-commit <hash1>
git status --porcelain                    # 确认只有 plugins.v2/... 和 tests/ 文件
git reset HEAD <无关文件>                 # 如有意外文件，移出暂存区
git commit -m "<原始提交信息>"

git cherry-pick --no-commit <hash2>
git status --porcelain
git commit -m "<原始提交信息>"
# ... 更多提交

# 或者简化方式（保留 "cherry picked from <hash>" 追踪）:
git cherry-pick <hash1>
git cherry-pick <hash2>

# === 阶段 3: 标记与推送 ======================================

# 3.1 标记上游已同步（消除 GitHub "N commits behind" 提示）
git merge -s ours upstream/main -m "sync: mark upstream as merged (cherry-pick complete)"

# 3.2 推送到远程
git push origin main
```

## 冲突处理

### 情况 1: 普通冲突（文件已在工作区中）

```bash
# cherry-pick 失败时，按以下步骤处理:

# 1. 列出冲突文件
git diff --name-only --diff-filter=U

# 2. 编辑冲突文件，手动合并标记区域:
#    <<<<<<< HEAD            ← 你的本地版本
#    =======                 ← 分隔线
#    >>>>>>> <hash>          ← 上游版本
#    保留想要的内容，删除所有标记行

# 3. 确认所有冲突已解决（无输出 = 干净）
git diff --name-only --diff-filter=U

# 4. 标记已解决并继续
git add <冲突文件1> <冲突文件2>
git cherry-pick --continue

# 5. 继续处理后续提交（如果有），然后执行 merge -s ours

# 备用: 放弃当前 cherry-pick 重来
git cherry-pick --abort
```

### 情况 2: 稀疏检出导致的冲突（tests 文件不在工作区）

⚠️ **这是曾经反复踩过的坑**：本仓库使用 sparse-checkout 精简了大量文件。有些 test 文件（如 `tests/test_integration.py`、`tests/test_verifier.py`）不在 sparse-checkout 范围内，cherry-pick 时 git 会因为找不到这些文件而报冲突。

```bash
# 1. 列出冲突文件，确认是稀疏检出导致
git diff --name-only --diff-filter=U
# 典型输出: tests/test_integration.py, tests/test_verifier.py

# 2. 临时将冲突文件加入 sparse-checkout
#    注意路径是从仓库根目录开始的，例如 /tests/test_verifier.py
git sparse-checkout add /tests/<冲突文件名>

# 3. 使用上游版本（theirs）解决冲突
git checkout --theirs <冲突文件>

# 4. 暂存已解决的文件
git add <冲突文件>

# 5. 确认冲突已全部解决
git diff --name-only --diff-filter=U   # 应无输出

# 6. 继续 cherry-pick
git cherry-pick --continue

# 7. 继续处理后续提交，最后执行 merge -s ours
```

## 验证结果

```bash
# 确认已追上上游（应为 0）
git rev-list --count HEAD..upstream/main

# 确认工作区干净
git status --porcelain
```

## 核心公式

```
同步三步骤:
  git cherry-pick <hash>                              # 只拿插件代码
  git merge -s ours upstream/main -m "sync: done"     # 消除 GitHub behind 提示
  git push origin main                                 # 推送
```

## 危险操作（绝对禁止）

这些命令会带回 400+ 个之前已删除的无关文件：

```bash
# ✗ 禁止使用普通 merge
git merge upstream/main

# ✗ 禁止使用 pull（等同于 fetch + merge）
git pull upstream main

# ✗ 禁止使用 rebase
git rebase upstream/main
```

## 踩坑要点速查

| 坑 | 现象 | 原因 | 正确做法 |
|----|------|------|----------|
| cherry-pick 后仍 behind | GitHub 显示 "N commits behind" | cherry-pick 产生新 hash，GitHub 不认 | cherry-pick 后必须 `merge -s ours` |
| merge -s ours 不是永久 | 过几天又 behind | 上游推送新提交，旧标记只对当时的 HEAD 生效 | 每次同步都重新执行 merge -s ours |
| sparse-checkout 冲突 | cherry-pick 报 tests 文件冲突 | tests 文件不在 sparse-checkout 中 | `sparse-checkout add` → `checkout --theirs` → `add` → `cherry-pick --continue` |
| cherry-pick 带进无关文件 | 提交中包含非插件文件 | 上游提交混合了插件代码和其他改动 | 用 `--no-commit` + `git status` 检查，只提交相关文件 |
| 顺序错误 | 先 merge -s ours 后无法 cherry-pick | merge -s ours 标记后 git 认为所有提交已处理 | **永远先 cherry-pick，再 merge -s ours** |
