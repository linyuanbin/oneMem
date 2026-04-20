## 跨 IDE 兼容性

同时支持 Claude Code 和 Cursor IDE：

| 特性            | Claude Code               | Cursor IDE                          |
|---------------|---------------------------|-------------------------------------|
| 会话 ID 字段      | `session_id`              | `conversation_id`                   |
| 工作目录字段        | `cwd`                     | `workspace_roots[0]`                |
| Transcript 格式 | `.jsonl`，`type`/`role` 字段 | `.jsonl`，`role` + `<user_query>` 标签 |

代码中已实现双格式兼容处理：

```python
# 会话 ID 获取
def get_session_id(stdin_data):
    return stdin_data.get("session_id") or stdin_data.get("conversation_id", "")


# 工作目录获取
def get_cwd(stdin_data):
    if "cwd" in stdin_data:
        return stdin_data["cwd"]
    workspace_roots = stdin_data.get("workspace_roots", [])
    if workspace_roots:
        return workspace_roots[0]
    return os.getcwd()
```

## 手动测试命令

```bash
# 测试加载 hook（Claude Code 格式）
echo '{"cwd":"/tmp","session_id":"s1","transcript_path":"/tmp/t.jsonl"}' | \
  python3 ~/.claude/plugins/onemem/scripts/onemem.py load

# 测试加载 hook（Cursor 格式）
echo '{"workspace_roots":["/tmp"],"conversation_id":"c1","transcript_path":"/tmp/t.jsonl"}' | \
  python3 ~/.claude/plugins/onemem/scripts/onemem.py load

# 测试保存 hook
echo '{"cwd":"/tmp","session_id":"s1","transcript_path":"/tmp/t.jsonl"}' | \
  python3 ~/.claude/plugins/onemem/scripts/onemem.py save

# 测试观察 hook
echo '{"cwd":"/tmp","session_id":"s1","tool_name":"Write","tool_input":{"file_path":"/tmp/test.py"}}' | \
  python3 ~/.claude/plugins/onemem/scripts/onemem.py observe

# 语法检查
python3 -m py_compile ~/.claude/plugins/onemem/scripts/onemem.py
```

## 错误处理策略

- **所有错误静默处理**：hook 退出码始终为 0，不阻塞 IDE 工作流
- **配置缺失时正常运行**：会话正常启动和结束，不加载/保存记忆
- **PowerMem 不可达时正常运行**：网络错误不影响 IDE 使用
- **MCP 错误返回文本**：错误信息作为 response content 返回

## 与 旧版 的区别

| 特性      | v0.1.0之前            | v1.0.0之后                          |
|---------|---------------------|-----------------------------------|
| Hook 事件 | SessionStart + Stop | SessionStart + PostToolUse + Stop |
| 记忆格式    | 纯文本                 | 结构化（类型、标题、概念、文件）                  |
| 检索方式    | 启动时全量注入             | 渐进式披露 + MCP 工具                    |
| 自动分类    | 无                   | 基于模式的 7 种类型分类                     |
| MCP 支持  | 无                   | search, get_memory, recent        |
