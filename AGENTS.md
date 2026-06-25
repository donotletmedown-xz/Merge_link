# AGENTS.md

本文件面向 AI 编程助手。阅读本文档前，默认你对本项目一无所知。以下内容基于仓库中的实际文件和代码，而非外部假设。

---

## 项目概述

Merge_link 是一个用于 **Clash / Mihomo** 的代理配置合并工具。它的核心任务是从本地模板读取基础配置（DNS、规则集、规则），再从多个节点配置 URL、VLESS 分享链接或 v2ray 订阅链接中提取代理节点，按来源生成「手选 + 自动选择」分组，最终合并输出为单一 YAML 配置文件 `merged_config.yaml`。

项目同时支持三种运行形态：

1. **GitHub Actions** 自动运行并上传结果到 Gist（推荐，零运维）。
2. **VPS 直接运行**：通过 `setup_cron.sh` 部署 crontab 定时执行。
3. **VPS 远程触发 Actions**：通过 `trigger_actions.sh` 调用 GitHub API 触发工作流。

---

## 技术栈

- **语言**：Python 3（工作流固定使用 3.11）。
- **唯一第三方依赖**：`pyyaml`。
- **网络请求**：仅使用 Python 标准库 `urllib.request`。
- **部署脚本**：Bash（`setup_cron.sh`、`setup_vnstat.sh`、`trigger_actions.sh`）。
- **CI/CD**：GitHub Actions（`.github/workflows/update-config.yml`）。
- **包管理**：无 `requirements.txt`、`pyproject.toml`、`setup.py` 等现代 Python 包管理文件；依赖在 CI 脚本和部署脚本中通过 `pip install pyyaml` 直接安装。

---

## 项目结构

```
Merge_link/
├── merge_clash.py              # 核心合并脚本（入口）
├── v2ray_parser.py             # 独立的 v2ray 订阅链接 / VLESS 解析工具
├── config_template.yaml        # 基础配置模板（DNS、规则集、规则，不含节点和分组）
├── run_test.py                 # 本地测试脚本：加载 test.env 并调用 merge_clash.py
├── setup_cron.sh               # VPS 直接部署脚本（创建 venv + crontab）
├── setup_vnstat.sh             # vnstat 每小时流量统计部署脚本（可选）
├── trigger_actions.sh          # VPS 远程触发 GitHub Actions 的脚本
├── .github/workflows/
│   └── update-config.yml       # GitHub Actions 工作流
├── .gitignore                  # 忽略敏感文件和输出文件
├── CLAUDE.md                   # 面向 Claude Code 的指引
├── README.md                   # 面向用户的中文使用文档
├── test.env                    # 本地测试环境变量（已 gitignore，请勿提交）
└── output/                     # 示例输出目录（部分历史产物）
```

---

## 代码组织与核心模块

### `merge_clash.py`（主入口）

全局配置均从环境变量读取，模块级常量包括：

- `TEMPLATE_FILE`：模板路径，默认 `config_template.yaml`。
- `NODE_URLS`：逗号分隔的节点配置 URL 列表。
- `VLESS_LINKS`：逗号分隔的 VLESS 分享链接。
- `V2RAY_SUB_URLS`：逗号分隔的 v2ray 订阅链接。
- `OUTPUT_FILE`：输出文件路径，默认 `merged_config.yaml`。

`main()` 的核心流程：

1. `load_template()` 加载本地模板。
2. 遍历 `NODE_URLS`：每个 URL 独立成组，组名为 `node-1`、`node-2`……
3. 遍历 `VLESS_LINKS`：通过 `parse_vless_uri()` 解析，统一成组 `vless`。
4. 遍历 `V2RAY_SUB_URLS`：通过 `fetch_v2ray_sub()` 获取并 base64 解码，再解析为 `v2` 组。
5. `create_unified_groups()` 创建统一分组 `手选-azheng` / `自动-azheng`。
6. `build_main_group()` 创建主分组 `节点选择`，引用 `DIRECT`、`REJECT`、统一分组和各来源分组。
7. 写入 `OUTPUT_FILE`。

关键函数：

- `load_template(path)`：读取本地 YAML 模板。
- `read_source(path_or_url)` / `fetch_url(url)`：读取本地文件或远程 URL，跳过 SSL 验证。
- `parse_vless_uri(uri)`：把 `vless://...` 解析为 Clash Meta 代理字典。支持传输层 `tcp/ws/grpc/h2/quic`，安全层 `none/tls/reality`。
- `merge_proxies(base, node_config, source_type)`：按 `name` 合并代理，重名时自动编号为 `-01`、`-02`……
- `create_source_groups(base, source_name, proxy_names)`：为某个来源创建「手选」和「自动」两个分组。
- `create_unified_groups(base, all_proxy_names, auto_names)`：创建跨来源的统一分组。
- `build_main_group(base, source_names)`：构建 `节点选择` 主分组。

兼容性处理：

- 同时支持 Clash 键名 `proxies` / `proxy-groups` 和 Mihomo 键名 `Proxy` / `ProxyGroup`。
- Windows 下强制 UTF-8 标准输出，避免 GBK 终端乱码。
- HTTP 请求禁用 SSL 验证（`ssl.CERT_NONE`），适配自签证书场景。
- User-Agent 固定为 `ClashForAndroid/2.5.12`。

### `v2ray_parser.py`（独立工具）

可单独运行的 v2ray 订阅解析器，提供命令行接口：

```bash
python v2ray_parser.py --url "https://example.com/sub"
python v2ray_parser.py --base64 "dmxlc3M6Ly8..."
python v2ray_parser.py --file subscription.txt
python v2ray_parser.py --url "..." --format json --output nodes.json
python v2ray_parser.py --url "..." --format clash --output proxies.yaml
```

该文件在 `merge_clash.py` 中**并未被导入**，属于独立辅助工具，二者各维护一份 VLESS 解析逻辑。修改 VLESS 解析时需要注意保持两份代码的一致性，或评估是否应复用同一段逻辑。

---

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `TEMPLATE_FILE` | 否 | 模板文件路径，默认 `config_template.yaml` |
| `NODE_URLS` | 三选一 | 逗号分隔的节点配置 URL |
| `VLESS_LINKS` | 三选一 | 逗号分隔的 VLESS 分享链接 |
| `V2RAY_SUB_URLS` | 三选一 | 逗号分隔的 v2ray 订阅链接 |
| `OUTPUT_FILE` | 否 | 输出文件路径，默认 `merged_config.yaml` |
| `GIST_TOKEN` | 仅 Actions | 具有 `gist` 权限的 GitHub Token |
| `GIST_ID` | 否 | 已存在的 Gist ID；首次运行可留空，工作流会输出新的 ID |
| `GITHUB_TOKEN` | 仅远程触发 | 具有 `workflow` 权限的 GitHub Token（`trigger_actions.sh` 使用） |

`NODE_URLS`、`VLESS_LINKS`、`V2RAY_SUB_URLS` 至少需要设置一个，否则 `merge_clash.py` 会直接退出。

---

## 构建与运行命令

### 安装依赖

```bash
pip install pyyaml
```

### 直接运行

```bash
NODE_URLS="https://a.com/nodes.yaml,https://b.com/nodes.yaml" \
VLESS_LINKS="vless://uuid@server:port?params#name" \
V2RAY_SUB_URLS="https://sub.example.com/sub" \
python merge_clash.py
```

### 本地测试

```bash
python run_test.py
```

`run_test.py` 会读取 `test.env`（格式同 `.env`，支持 `#` 注释），将其中变量注入环境后调用 `merge_clash.py`。`test.env` 已加入 `.gitignore`，不应提交。

### 输出产物

- `merged_config.yaml`：合并后的完整 Clash / Mihomo 配置。
- `merge_clash.log`：VPS 部署时的运行日志（已 gitignore）。
- `trigger_actions.log`：远程触发 Actions 的日志（已 gitignore）。

---

## 测试策略

- **无单元测试框架**：项目没有 `pytest`、`unittest` 等正式测试套件。
- **本地验证方式**：修改代码后运行 `python run_test.py`，观察是否能正确生成 `merged_config.yaml`。
- **核心验证点**：
  - 模板能否正常加载；
  - 节点 URL / VLESS / v2ray 订阅是否能解析；
  - 重名节点是否能自动编号；
  - 最终 YAML 是否包含 `proxies`、`proxy-groups`、`rules` 三大键；
  - `节点选择` 主分组引用的子分组是否已在前文定义（脚本通过将其追加到末尾避免前向引用问题）。

---

## 代码风格指南

- **缩进**：4 个空格。
- **编码**：UTF-8；Windows 环境下脚本会强制 stdout/stderr 为 UTF-8。
- **注释与文档**：使用中文 docstring 和行内注释。
- **函数组织**：按功能拆分，保持 `merge_clash.py` 中的函数纯函数化（除 `main()` 外尽量避免副作用）。
- **变量命名**：使用下划线命名法（snake_case），配置键名保持与 Clash 一致。
- **兼容性编码**：读写 YAML 统一使用 `encoding="utf-8"`；写入时 `yaml.dump(..., allow_unicode=True, default_flow_style=False, sort_keys=False)`。
- **错误处理**：网络或解析失败时打印警告并 `continue`，避免单点失败导致整个流程中断。
- **重复代码警惕**：`merge_clash.py` 和 `v2ray_parser.py` 各自维护了一套 VLESS 解析逻辑，修改时需要同步评估。

---

## 部署流程

### GitHub Actions

工作流 `.github/workflows/update-config.yml`：

- 触发条件：每 2 小时定时运行（UTC），或 `workflow_dispatch` 手动触发。
- 步骤：检出代码 → 安装 Python 与 `pyyaml` → 运行 `merge_clash.py` → 通过 GitHub API 创建或更新 Gist。
- Secret 管理：在仓库 Settings → Secrets → Actions 中配置 `NODE_URLS`、`VLESS_LINKS`、`V2RAY_SUB_URLS`、`GIST_TOKEN`、`GIST_ID`。

### VPS 直接运行

```bash
bash setup_cron.sh
```

脚本会：

1. 安装 `python3`、`pip`、`venv`。
2. 创建虚拟环境并安装 `pyyaml`。
3. 立即运行一次 `merge_clash.py`。
4. 添加 crontab，每 2 小时执行一次。

注意：该脚本使用 `apt-get`，面向 Debian / Ubuntu 系统。

### VPS 远程触发 Actions

```bash
# 手动触发一次
bash trigger_actions.sh

# 安装 / 卸载 / 查看定时任务
bash trigger_actions.sh --install
bash trigger_actions.sh --uninstall
bash trigger_actions.sh --status
```

Token 读取优先级：环境变量 `GITHUB_TOKEN` > 脚本目录下的 `.github_token` 文件。`.github_token` 已加入 `.gitignore`。

---

## 安全注意事项

1. **敏感文件已 gitignore**：`merged_config.yaml`、`merge_clash.log`、`node_url.yaml`、`.github_token`、`test.env`、`merged_config2.yaml`、`out*/` 均不应提交。
2. **凭证不外泄**：`test.env` 中可能包含节点 URL、UUID、Token 等敏感信息；修改 AGENTS.md 或 README 时不要复制其中的真实值。
3. **SSL 验证已禁用**：`fetch_url()` 使用 `ssl.CERT_NONE` 并关闭 `check_hostname`，仅用于自签证书场景，不要在需要高安全性的通用网络库中复用该模式。
4. **Token 权限最小化**：
   - `GIST_TOKEN` 只需要 `gist` 的读写权限。
   - 远程触发 Actions 的 `GITHUB_TOKEN` 需要 `workflow` 和 `gist` 权限。
5. **Gist 默认公开**：Actions 工作流创建 Gist 时设置 `"public": true`，配置文件中包含代理服务器信息，请注意隐私风险。
6. **避免在日志中打印完整 URL/Token**：现有代码会打印 VLESS 链接前 60 字符及节点名，注意日志文件权限与清理。

---

## 常见修改场景

- **新增支持的安全层 / 传输层**：需要同时修改 `merge_clash.py` 的 `parse_vless_uri()` 和 `v2ray_parser.py` 的同名函数（或重构为公共模块）。
- **调整分组策略**：修改 `create_source_groups()`、`create_unified_groups()`、`build_main_group()`。
- **更换规则集来源**：修改 `config_template.yaml` 中的 `rule-providers` URL。
- **调整定时频率**：修改 `.github/workflows/update-config.yml` 的 `cron` 表达式，或修改 `setup_cron.sh` / `trigger_actions.sh` 中的 crontab 行。
- **新增输出字段**：注意 `yaml.dump` 的 `sort_keys=False`，以保持人类可读性。
