# sync-upstream.ps1
# 从 InfinityPacer 上游同步 subscribeassistantenhanced 插件更新
# 策略: cherry-pick 上游提交 + merge -s ours 标记已同步
# 用法: .\sync-upstream.ps1 [-Push] [-Force]
#   -Push   自动推送（仅无冲突时生效）
#   -Force  强制跳过冲突检查（不推荐）

param(
    [switch]$Push,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# 注意: 本地已从 subscribeassistantenhanced 重命名为 SubscribeAssistantEnhancedPro
# 上游仍用旧名 subscribeassistantenhanced，所以两个路径都要监控
$PluginPathLocal  = "plugins.v2/SubscribeAssistantEnhancedPro"
$PluginPathUpstream = "plugins.v2/subscribeassistantenhanced"
$Upstream         = "upstream"
$UpstreamBranch   = "main"
$TestPath         = "tests"

# 检查上游差异时使用的路径（上游用旧名）
$DiffPaths = @($PluginPathUpstream, $TestPath)

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  sync-subscribeassistantenhanced           " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  策略: cherry-pick 上游提交 + merge -s ours" -ForegroundColor Cyan
Write-Host "  上游路径: $PluginPathUpstream → 本地: $PluginPathLocal" -ForegroundColor Cyan
Write-Host "  同步范围: $PluginPathUpstream + $TestPath" -ForegroundColor Cyan
Write-Host ""

# 1. 检查工作区是否干净
Write-Host "[1/6] 检查工作区状态..." -ForegroundColor Yellow
$status = git status --porcelain 2>$null
if ($status) {
    Write-Host "警告: 工作区有未提交的变更，建议先提交或暂存:" -ForegroundColor Red
    Write-Host ($status -join "`n")
    Write-Host ""
    Write-Host "  [C] 中止，手动提交/暂存后重试"
    Write-Host "  [Y] 继续（未提交的变更可能导致冲突）"
    $confirm = Read-Host "  选择 (C/Y)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "已取消。建议先: git add -A; git commit -m 'local changes'" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  工作区干净 ✓" -ForegroundColor Green
Write-Host ""

# 2. 拉取上游
Write-Host "[2/6] 拉取上游 ($Upstream/$UpstreamBranch)..." -ForegroundColor Yellow
git fetch $Upstream $UpstreamBranch
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 拉取上游失败，请检查网络或 upstream 远程配置。" -ForegroundColor Red
    exit 1
}
Write-Host "  拉取完成 ✓" -ForegroundColor Green
Write-Host ""

# 3. 获取上游新提交列表
Write-Host "[3/6] 检查上游新提交..." -ForegroundColor Yellow

$upstreamCommits = git log --oneline --no-merges HEAD..$Upstream/$UpstreamBranch 2>$null
if (-not $upstreamCommits) {
    Write-Host "  没有新的上游提交，已是最新。 ✓" -ForegroundColor Green
    exit 0
}

$commitCount = ($upstreamCommits | Measure-Object -Line).Lines
Write-Host "  发现 $commitCount 个上游新提交:" -ForegroundColor Cyan
foreach ($line in $upstreamCommits) {
    Write-Host "    - $line" -ForegroundColor Gray
}
Write-Host ""

# 4. 检查这些提交是否涉及 subscribeassistantenhanced
Write-Host "[4/6] 分析提交范围..." -ForegroundColor Yellow

$affectedPaths = git diff --name-only HEAD..$Upstream/$UpstreamBranch -- $PluginPathUpstream $TestPath 2>$null

if (-not $affectedPaths) {
    # ===== 无插件变更：直接 merge -s ours =====
    Write-Host "  上游新提交不涉及 $PluginPathUpstream / $TestPath，直接标记同步。 ✓" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  执行 git merge -s ours $Upstream/$UpstreamBranch..." -ForegroundColor Gray
    git merge -s ours $Upstream/$UpstreamBranch -m "sync: mark upstream as merged (no plugin changes)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误: merge -s ours 失败。" -ForegroundColor Red
        exit 1
    }
    Write-Host "  已标记同步 ✓" -ForegroundColor Green
} else {
    # ===== 有插件变更：cherry-pick + merge -s ours =====
    Write-Host "  涉及的文件:" -ForegroundColor Cyan
    foreach ($path in $affectedPaths) {
        Write-Host "    [+] $path" -ForegroundColor Gray
    }
    Write-Host ""

    # 5. Cherry-pick 每个上游提交
    Write-Host "[5/6] Cherry-pick 上游提交..." -ForegroundColor Yellow

    # 获取提交哈希列表（从旧到新）
    $commitHashes = git log --oneline --no-merges --reverse HEAD..$Upstream/$UpstreamBranch --format="%H" 2>$null
    $commitHashes = $commitHashes -split "`n" | Where-Object { $_ -match '^[a-f0-9]{40}$' }

    $cherryFailed = $false
    $cherryCount = 0

    foreach ($hash in $commitHashes) {
        $shortHash = $hash.Substring(0, 7)
        $commitMsg = git log --format="%s" -1 $hash
        Write-Host "  Cherry-pick: $shortHash ($commitMsg)" -ForegroundColor Gray

        $cherryOutput = git cherry-pick --no-commit $hash 2>&1
        $cherryExitCode = $LASTEXITCODE

        if ($cherryExitCode -ne 0) {
            Write-Host ""
            Write-Host "============================================" -ForegroundColor Red
            Write-Host "  !! Cherry-pick 冲突: $shortHash" -ForegroundColor Red
            Write-Host "============================================" -ForegroundColor Red
            Write-Host ""

            # 列出冲突文件
            Write-Host "冲突文件:" -ForegroundColor Yellow
            $conflictFiles = git diff --name-only --diff-filter=U 2>$null
            if ($conflictFiles) {
                foreach ($f in $conflictFiles) {
                    Write-Host "  [!] $f" -ForegroundColor Red
                    # 统计冲突区域
                    if (Test-Path $f) {
                        $conflictCount = (Select-String -Path $f -Pattern "^<<<<<<< " -AllMatches 2>$null).Matches.Count
                        if ($conflictCount -and $conflictCount -gt 0) {
                            Write-Host "      $conflictCount 处冲突" -ForegroundColor Gray
                        }
                    }
                }
            }
            Write-Host ""

            Write-Host "解决步骤:" -ForegroundColor Cyan
            Write-Host "  1. 编辑冲突文件，解决 <<<<<<< / ======= / >>>>>>> 标记处"
            Write-Host "  2. git add <已解决的文件>"
            Write-Host "  3. git cherry-pick --continue  或  git cherry-pick --abort 放弃"
            Write-Host "  4. 手动 cherry-pick 剩余提交，然后运行 merge -s ours"
            Write-Host ""
            Write-Host "剩余未处理的提交:" -ForegroundColor Red

            # 显示剩余提交
            $remaining = git log --oneline --no-merges HEAD..$Upstream/$UpstreamBranch 2>$null
            if ($remaining) {
                foreach ($line in $remaining) {
                    Write-Host "  - $line" -ForegroundColor Red
                }
            }
            Write-Host ""
            Write-Host "解决完成后依次执行:" -ForegroundColor Gray
            Write-Host "  git cherry-pick <hash>    # 继续 cherry-pick 剩余提交" -ForegroundColor Gray
            Write-Host "  git merge -s ours $Upstream/$UpstreamBranch -m 'sync: mark upstream as merged'" -ForegroundColor Gray
            $cherryFailed = $true
            exit 1
        }

        # Cherry-pick 成功，检查暂存文件是否都在预期范围内
        $stagedFiles = git diff --cached --name-only 2>$null
        $unexpected = @()
        foreach ($f in $stagedFiles) {
            # 允许上游旧路径 (subscribeassistantenhanced) 和本地新路径 (SubscribeAssistantEnhancedPro)
            if ($f -notmatch "^($([regex]::Escape($PluginPathUpstream))|$([regex]::Escape($PluginPathLocal))|$([regex]::Escape($TestPath)))/") {
                $unexpected += $f
                Write-Host "    警告: 发现非预期文件 $f，已取消暂存" -ForegroundColor Yellow
                git reset HEAD $f 2>$null
            }
        }

        # 提交仅包含插件相关文件
        git commit -m $commitMsg 2>$null
        if ($LASTEXITCODE -eq 0) {
            $cherryCount++
            Write-Host "    已 cherry-pick ✓" -ForegroundColor Green
        } else {
            # 可能是空提交（所有变更都已被过滤）
            Write-Host "    跳过（无插件相关变更）" -ForegroundColor Gray
        }
    }

    if ($cherryCount -gt 0) {
        Write-Host "  共 cherry-pick $cherryCount 个提交 ✓" -ForegroundColor Green
    }
    Write-Host ""
    
    # 检查是否有上游旧路径的变更需要手动迁移到新路径
    $oldPathChanges = git diff HEAD~$cherryCount..HEAD --name-only -- $PluginPathUpstream 2>$null
    if ($oldPathChanges) {
        Write-Host "============================================" -ForegroundColor Yellow
        Write-Host "  !! 注意: 上游变更在旧路径下" -ForegroundColor Yellow
        Write-Host "  $PluginPathUpstream/ → 需手动迁移到:" -ForegroundColor Yellow
        Write-Host "  $PluginPathLocal/" -ForegroundColor Yellow
        Write-Host "============================================" -ForegroundColor Yellow
        Write-Host ""
        foreach ($f in $oldPathChanges) {
            Write-Host "  [?] $f" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "  请手动将改动应用到本地新路径，完成后:" -ForegroundColor Gray
        Write-Host "    1. 删除旧路径文件: git rm -r $PluginPathUpstream  (如不需要保留)" -ForegroundColor Gray
        Write-Host "    2. 修改新路径文件: 手动编辑 $PluginPathLocal/" -ForegroundColor Gray
        Write-Host "    3. 提交: git add -A; git commit --amend" -ForegroundColor Gray
        Write-Host ""
    }

    # 6. merge -s ours 标记已同步
    Write-Host "[6/6] 标记上游同步..." -ForegroundColor Yellow
    Write-Host "  执行 git merge -s ours $Upstream/$UpstreamBranch..." -ForegroundColor Gray

    $mergeOutput = git merge -s ours $Upstream/$UpstreamBranch -m "sync: mark upstream as merged (cherry-pick complete)" 2>&1
    $mergeExitCode = $LASTEXITCODE

    if ($mergeExitCode -ne 0) {
        Write-Host "错误: merge -s ours 失败。" -ForegroundColor Red
        Write-Host $mergeOutput
        exit 1
    }
    Write-Host "  已标记同步 ✓" -ForegroundColor Green
}

Write-Host ""

# 推送
if ($Push) {
    Write-Host "推送中..." -ForegroundColor Yellow
    git push origin main
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  已推送 ✓" -ForegroundColor Green
    } else {
        Write-Host "  推送失败，请手动执行 git push origin main" -ForegroundColor Red
    }
} else {
    Write-Host "提示: 使用 -Push 参数可自动推送。" -ForegroundColor Gray
    Write-Host "      手动推送: git push origin main" -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  同步完成！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
