### MCP 工具名称

在 Claude Code 内部，工具名称为：

| 显示名称 | MCP 工具名 | Server 名称 |
|----------|-----------|-------------|
| search | `search` | `memory-search` |
| get_memory | `get_memory` | `memory-search` |
| recent | `recent` | `memory-search` |

完整调用路径：`memory-search.search`、`memory-search.get_memory`、`memory-search.recent`

- 会话启动时会显示 "onemem: memory index loaded..." 提示
- 可直接调用 MCP 工具（无需额外配置）

## PowerMem 参数映射

插件使用特定的参数映射策略：

| PowerMem 参数 | 值来源 | 说明 |
|---------------|--------|------|
| `agent_id` | 项目身份 | `git remote get-url origin` 或 `basename(cwd)` |
| `run_id` | 会话 ID | Claude Code: `session_id`，Cursor: `conversation_id` |
| `user_id` | 用户标识 | 配置文件 `user_id` 或随机 UUID |
| `user` | 用户邮箱 | 配置文件 `user`，作为 header 发送 |

**设计说明：**

- **agent_id = 项目身份**：**主要隔离维度**，同一项目在不同 IDE/会话中共享记忆
- **run_id = session_id**：仅用于**追溯记录**，保存时存储，搜索时不作为过滤条件
- **配置文件中的 agent_id 字段不再使用**：项目身份从 git/cwd 动态获取

**跨会话/跨 IDE 共享：**

由于 `agent_id` 是项目身份（git remote URL），所有使用同一项目的会话都会：
- 搜索时：获取该项目所有历史记忆（不受 session_id 限制）
- 保存时：记录当前 session_id（用于追溯）

这样实现了：
- ✅ 同项目跨会话共享记忆
- ✅ 同项目跨 IDE 共享记忆（Claude Code ↔ Cursor）
- ✅ 不同项目记忆相互隔离

## MCP 工具使用

插件通过 MCP 协议提供三个搜索工具。

### 如何触发 MCP 查询

在 Claude Code 中，MCP 工具安装后自动可用，触发方式：

**方式一：直接请求 Claude 查询记忆**

在对话中直接说：

```
帮我搜索记忆中关于认证实现的内容
```

```
查看最近 7 天的记忆记录
```

```
获取记忆 ID 123 和 456 的详细内容
```

Claude 会自动识别意图并调用对应的 MCP 工具。

**方式二：明确指定工具**

```
使用 memory-search 的 search 工具搜索 "bugfix" 类型的记忆
```

**方式三：查看索引后按需获取**

会话启动时会显示记忆索引表格：

```
### Recent Observations Index

| ID | Type | Title | Date |
|----|------|-------|------|
| #123 | 🟢 | Add authentication module | 2024-01-15 |
| #124 | 🟡 | Fix login timeout bug | 2024-01-14 |
| #125 | 🟤 | Decision: Use JWT for auth | 2024-01-13 |

💡 **Progressive Disclosure:** Use MCP search tools to fetch full details on-demand.
```

然后请求获取详情：

```
获取 #123 和 #125 的完整内容
```

### search（搜索记忆）

按关键词搜索记忆，可指定类型过滤：

**示例请求：**

```
搜索记忆中关于 "API endpoint" 的内容
```

```
搜索所有 bugfix 类型的记忆
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `query` | string | 搜索关键词（可留空搜索全部） |
| `type` | string | 类型过滤：gotcha, decision, bugfix, feature, discovery, change |
| `limit` | integer | 返回数量限制（默认 20） |

### get_memory（获取详情）

根据 ID 获取记忆完整内容。

**示例请求：**

```
获取记忆 #123 的详细内容
```

```
查看 ID 为 123、456、789 的记忆详情
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ids` | array[int] | ✅ | 记忆 ID 数组 |

返回内容包含：完整文本、类型、标题、概念、关联文件、保存时间。

### recent（最近记忆）

获取当前项目的最近记忆时间线。

**示例请求：**

```
查看最近 30 天的记忆
```

```
显示最近 10 条记忆记录
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `days` | integer | 回溯天数（默认 7） |
| `limit` | integer | 返回数量限制（默认 10） |