中文| [English](README.md)

# OneMem 使用

OneMem提供跨 IDE 会话记忆插件，支持 Claude Code 和 Cursor IDE，基于 [PowerMem](https://github.com/oceanbase/powermem) 实现。

```
  工作流程：

  Session A (Claude Code)          Session B (Cursor)
       │                                │
       │ 保存: agent_id=project         │ 搜索: agent_id=project
       │       run_id=session_A         │       run_id="" (获取所有)
       │                                │
       └────────────────────────────────┘
                      ↓
                PowerMem
                agent_id=project
                (共享所有历史记忆)

```

## 功能概述

### 核心能力

| 功能       | 说明                           |
|----------|------------------------------|
| 会话启动加载   | 加载记忆索引，采用渐进式披露策略             |
| 会话过程捕获   | 通过 PostToolUse hook 自动捕获工具执行 |
| 会话结束保存   | 从 transcript 提取结构化观察并持久化     |
| MCP 搜索工具 | 提供按需查询记忆的能力                  |

### 渐进式披露

避免在会话启动时注入过多上下文，采用三层检索模式：

1. **启动时索引** — 显示记忆列表表格（ID、类型、标题、日期，约 50-100 tokens）
2. **MCP 工具查询** — `recent` 返回带元数据的结构化列表
3. **详情按需获取** — `get_memory` 获取完整内容（约 500-1000 tokens）

### 观察自动分类

基于内容模式的自动类型检测：

| 类型        | 图标 | 触发关键词                                       |
|-----------|----|---------------------------------------------|
| Gotcha    | 🔴 | timeout, failed, error, crash, gotcha, 边界情况 |
| Bugfix    | 🟡 | fix, fixed, bug, patch, resolve, 修复         |
| Decision  | 🟤 | decided, chose, architecture, strategy, 决定  |
| Feature   | 🟢 | add, added, implement, create, build, 新增    |
| Discovery | 🟣 | found, discovered, learned, observed, 发现    |
| Trade-off | ⚖️ | compromise, balance, pro/con, 权衡            |
| Change    | 🔵 | modified, updated, refactored（默认类型）         |

# 快速开始

## 一、Claude Code快速安装

### 1. 添加插件市场

```
/plugin marketplace add linyuanbin/oneMem
```

### 2. 安装插件

```
/plugin install onemem@lin

/reload-plugins
```

安装完成后，以下功能会自动生效：

| 功能                | 自动配置 | 说明                      |
|-------------------|------|-------------------------|
| SessionStart hook | ✅    | 会话启动时加载记忆索引             |
| PostToolUse hook  | ✅    | Write/Edit/Bash 执行后捕获观察 |
| Stop hook         | ✅    | 会话结束时保存记忆               |
| MCP 搜索工具          | ✅    | 安装后自动注册，无需手动配置          |

### 3. 配置 PowerMem 连接（必须）

插件需要连接 PowerMem 服务才能正常工作：

```bash
mkdir -p ~/.oneMem
cat > ~/.oneMem/settings.json << 'EOF'
{
  "powermem_url": "https://your-powermem-instance.com",
  "api_key": "your-api-key",
  "user": "your-email"
}
EOF
```

**注意：** 如果没有配置 PowerMem，插件会静默跳过所有记忆操作，不影响 IDE 正常使用。

* 配置字段说明

| 字段             | 必填 | 说明                                   |
|----------------|----|--------------------------------------|
| `powermem_url` | ✅  | PowerMem 服务地址                        |
| `api_key`      | ✅  | API 密钥，作为 `X-API-Key` header 发送      |
| `user`         | ✅  | 用户邮箱，作为 `Powermem-User-Id` header 发送 |
| `user_id`      | ❌  | 用户标识符（可选，默认随机 UUID）                  |
| `index_limit`  | ❌  | 启动时加载的最大记忆数（默认 20）                   |
| `index_days`   | ❌  | 索索回溯天数（默认 7）                         |

* 环境变量覆盖

可通过 `ONEMEM_CONFIG` 环境变量指定配置文件路径：

```bash
export ONEMEM_CONFIG=/path/to/custom/settings.json
```

* 验证安装

安装完成后，可通过以下方式验证：

```bash
# 查看 plugin.json 是否正确
cat ~/.claude/plugins/onemem/.claude-plugin/plugin.json

# 应显示：
# {
#   "name": "onemem",
#   "hooks": "./hooks/hooks.json",
#   "mcpServers": "./mcp/mcp.json"
# }
```

在 Claude Code 会话中，MCP 工具会自动可用：[CMP渐进式加载触发方式](./MCP.md)

## Hook 事件说明

| Hook 事件        | 触发时机                | 功能                    |
|----------------|---------------------|-----------------------|
| `SessionStart` | 会话启动、清空、压缩时         | 加载记忆索引                |
| `PostToolUse`  | Write/Edit/Bash 执行后 | 捕获工具执行观察              |
| `Stop`         | 会话结束时               | 保存 transcript 中的结构化观察 |

### PostToolUse 捕获内容

针对不同工具类型的捕获策略：

| 工具         | 捕获内容                |
|------------|---------------------|
| Write/Edit | 文件路径 + 变更描述         |
| Bash       | 命令 + 输出摘要（前 200 字符） |
| Read       | 文件路径                |
| 其他         | 工具输入 JSON（前 200 字符） |

**跳过的工具：** Glob, Grep, LSP, TaskOutput, TaskList, TaskGet（信息价值较低）

## 二、Cursor IDE 使用指南

Cursor IDE 支持 Claude Code 的 hooks 格式，安装方式略有不同。
（如果本地使用claude code安装过该插件，Cursor会自动识别，无需重复安装，仅需要完成下面第二步的MCP配置即可）

### 方式一：手动配置 Hooks（推荐）

Cursor 目前需要手动配置 hooks，步骤如下：

注意：cursor能够识别到claude code安装的插件,检查方式：cursor -> 首选项 -> Cursor Settings -> Hooks (
页面看是否有相关hook配置),此时如果识别到可直接跳过步骤1，直接到步骤 -> 2. 配置 MCP 工具

#### 1. 创建 Hooks 配置文件

在项目根目录创建 `.cursor/hooks.json`：

```bash
# 从插件目录复制 hooks 配置
mkdir -p .cursor
cat > .cursor/hooks.json << 'EOF'
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/onemem/scripts/onemem.py load",
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/onemem/scripts/onemem.py observe",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/onemem/scripts/onemem.py save",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
EOF
```

**注意：** 需要将 `/path/to/onemem/scripts/onemem.py` 替换为实际路径，例如：

- 克隆仓库后的路径：`/Users/yourname_worspace/oneMem/scripts/onemem.py`
- 或将脚本复制到固定位置：`~/.local/bin/onemem.py`

#### 2. 配置 MCP 工具（可选）

如果需要 MCP 搜索工具，在 Cursor 设置中添加 MCP server：

**Cursor Settings → MCP → Add Server:**

```json
{
  "name": "memory-search",
  "command": "python3",
  "args": [
    "/path/to/onemem/scripts/onemem.py",
    "mcp"
  ]
}
```

#### 3. 配置 PowerMem

与 Claude Code 相同，创建 `~/.oneMem/settings.json`。

### 方式二：克隆插件仓库

(如果本地没有claude code安装过该插件则使用方式二)
将插件仓库克隆到本地：

```bash
# 克隆仓库
git clone https://github.com/linyuanbin/oneMem.git

# 配置 hooks（使用绝对路径）
mkdir -p .cursor
cat > .cursor/hooks.json << 'EOF'
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [{"type": "command", "command": "python3 /Users/yourname_worspace/oneMem/scripts/onemem.py load", "timeout": 15}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [{"type": "command", "command": "python3 /Users/yourname_worspace/oneMem/scripts/onemem.py observe", "timeout": 10}]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "python3 /Users/yourname_worspace/oneMem/scripts/onemem.py save", "timeout": 15}]
      }
    ]
  }
}
EOF

# 配置 MCP（在 Cursor Settings 中）
# command: python3
# args: ["~/.claude/plugins/onemem/scripts/onemem.py", "mcp"]
```

### Cursor vs Claude Code 对比

| 特性         | Claude Code                | Cursor IDE        |
|------------|----------------------------|-------------------|
| 插件安装       | `/plugin install` 命令       | 手动配置 hooks.json   |
| MCP 配置     | plugin.json 自动注册           | Settings 中手动添加    |
| Hooks 路径   | `${CLAUDE_PLUGIN_ROOT}` 变量 | 需要写绝对路径           |
| Session ID | `session_id`               | `conversation_id` |
| 工作目录       | `cwd`                      | `workspace_roots` |

### Cursor Hooks 配置位置

| 位置  | 作用范围 | 文件路径                   |
|-----|------|------------------------|
| 项目级 | 当前项目 | `.cursor/hooks.json`   |
| 用户级 | 所有项目 | `~/.cursor/hooks.json` |

**推荐使用项目级配置**，便于不同项目使用不同插件。

## 常见问题

### Q: 为什么配置文件中没有 agent_id？

**A:** agent_id 动态获取项目身份（git remote URL 或 cwd basename），确保：

- 同一项目在不同 IDE 中共享记忆
- 不同项目的记忆相互隔离
- 无需手动配置项目标识

### Q: PowerMem 的 run_id 是什么？

**A:** run_id 存储会话 ID，用于：

- 追溯记忆来源的具体会话
- 理论上可按会话维度查询历史
- 与 PowerMem 原设计的 run 概念对应

### Q: 如何查看当前项目的记忆？

**A:** 使用 MCP 工具：

1. `search({"query": ""})` — 搜索当前项目所有记忆
2. `recent({"days": 30})` — 查看最近 30 天的记忆时间线

### Q: 记忆会占用多少上下文空间？

**A:** 渐进式披露设计：

- 启动时仅注入索引表格（约 50-100 tokens）
- 详情通过 MCP 工具按需获取（每条约 500-1000 tokens）
- 用户主动查询时才消耗更多上下文