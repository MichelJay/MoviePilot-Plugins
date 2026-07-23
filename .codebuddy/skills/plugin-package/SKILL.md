---
name: plugin-package
description: This skill packages a MoviePilot plugin into a deployable .zip file. It should be used when the user asks to package, bundle, or zip a plugin for deployment, when they need to build the plugin frontend before packaging, or when preparing a plugin release. It handles frontend build (yarn/npm), excludes node_modules and __pycache__, and outputs to an output/ directory.
---

# MoviePilot 插件打包

## 概述

将 `plugins.v2/` 下的任意插件打包为可部署的 `.zip` 文件。自动处理前端构建（如果有 `frontend/` 子目录），排除 `node_modules`、`__pycache__` 和 `.pyc` 文件。

输出文件: `output/<插件名>_<版本号>.zip`

## 何时触发

当用户提出以下请求时使用本 skill:

- "打包插件"
- "打包 SubscribeAssistantEnhancedPro"
- "把这个插件打成 zip"
- "构建插件"
- "准备发布/部署插件"
- "package / bundle the plugin"

## 执行方式

### 脚本自动化（推荐）

```bash
# 直接指定插件名
python .codebuddy/skills/plugin-package/scripts/package-plugin.py --plugin SubscribeAssistantEnhancedPro

# 跳过前端构建（如果已手动构建过）
python .codebuddy/skills/plugin-package/scripts/package-plugin.py --plugin SubscribeAssistantEnhancedPro --skip-frontend
```

### 手动执行（AI 同等方式）

```bash
# 1. 前端构建（如果有 frontend/package.json）
if [ -f "plugins.v2/SubscribeAssistantEnhancedPro/frontend/package.json" ]; then
    cd plugins.v2/SubscribeAssistantEnhancedPro/frontend
    yarn install && yarn build
    cd ../../..
fi

# 2. 使用 Python 脚本打包
python .codebuddy/skills/plugin-package/scripts/package-plugin.py --plugin SubscribeAssistantEnhancedPro
```

## 打包流程

1. **前端构建** — 如果存在 `frontend/package.json`，自动选择 yarn/npm 构建
2. **收集文件** — 遍历插件目录，排除无用文件
3. **创建 zip** — 保持 `plugins.v2/<插件名>/` 目录结构，使用正斜杠路径分隔符
4. **输出结果** — 打印 zip 路径和大小

## 排除规则

| 排除项 | 原因 |
|--------|------|
| `frontend/node_modules/` | 体积巨大，部署时用不到 |
| `__pycache__/` | Python 字节码缓存 |
| `*.pyc` | 编译文件 |
| `frontend/src/` | 源代码，只需包含构建产物 |
| `frontend/package.json` / `yarn.lock` / `package-lock.json` | 不需要部署 |
| `.git/` / `.vscode/` | 开发工具文件 |

