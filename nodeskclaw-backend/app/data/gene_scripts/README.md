# DeskClaw AI 工具脚本

AI 员工可直接通过 bash 调用的 Python CLI 工具脚本。纯标准库实现，无第三方依赖。

## 目录结构

```
gene_scripts/
  _api_client.py             # 公共 HTTP 客户端（认证、错误处理）
  deskclaw_blackboard.py     # 黑板操作（内容、任务、目标、帖子）
  deskclaw_shared_files.py   # 共享文件管理
  deskclaw_topology.py       # 拓扑查询
  deskclaw_performance.py    # 效能统计
  deskclaw_proposals.py      # 审批提案
  deskclaw_gene_discovery.py # 基因市场
  README.md
```

## 环境变量

所有脚本通过以下环境变量认证，由框架在启动 agent 时注入：

| 变量 | 说明 |
|------|------|
| `DESKCLAW_API_URL` | Backend API 地址（如 `http://localhost:4510/api/v1`） |
| `DESKCLAW_TOKEN` | 实例 proxy_token |
| `DESKCLAW_WORKSPACE_ID` | 当前工作区 ID |
| `DESKCLAW_INSTANCE_ID` | 当前实例 ID（可选，部分脚本的默认值） |

## 使用方式

```bash
python3 ~/.deskclaw/tools/deskclaw_blackboard.py list_tasks --status pending
python3 ~/.deskclaw/tools/deskclaw_blackboard.py create_task --title "审查文档" --priority high
python3 ~/.deskclaw/tools/deskclaw_shared_files.py list_files --path /
python3 ~/.deskclaw/tools/deskclaw_shared_files.py write_file --filename hello.txt --content "Hello World" --parent-path /reports --content-type text/plain
python3 ~/.deskclaw/tools/deskclaw_topology.py get_reachable --instance-id <id>
python3 ~/.deskclaw/tools/deskclaw_gene_discovery.py search --keyword "blackboard"
```

每个脚本均支持 `--help` 查看完整用法。

## 设计原则

- 纯标准库（`urllib.request` + `json`），无需 `pip install`
- 输出 JSON，方便 agent 解析
- 错误时返回非零退出码 + JSON 错误信息
- 通过 `_api_client.py` 共享认证和 HTTP 请求逻辑

## 部署

基因安装时，GeneInstallAdapter 将脚本部署到实例的 `~/.deskclaw/tools/` 目录。
`_api_client.py` 作为共享模块一同部署，所有脚本通过相对导入使用。
