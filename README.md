# Merge_link

Clash / Mihomo 代理配置合并工具。从本地模板读取基础配置（规则、DNS、规则集），再从多个节点 URL、VLESS 分享链接和 v2ray 订阅链接中提取代理节点，按来源生成分组，合并输出为单一 YAML 配置文件，并可自动上传至 GitHub Gist 作为订阅链接使用。

## 功能特性

- 从本地模板文件读取基础配置（DNS、规则集、规则），无需远程获取
- 支持从多个节点 URL 合并代理节点
- 支持 VLESS 分享链接直接解析为 Clash Meta 代理节点
- 支持 v2ray 订阅链接（base64 编码的 VLESS 链接列表）
- 按来源自动分组：`node-*`、`vless-*`、`v2-*`
- 统一分组：`手选-azheng`（手动选择）、`自动-azheng`（自动选择延迟最低）
- 负载均衡分组：`hash-node`、`hash-vless`、`hash-v2`（一致性哈希策略）
- 重名节点自动添加来源后缀（`-node`、`-vless`、`-v2`）
- 兼容 Clash 和 Mihomo 的键名格式（`proxies`/`Proxy`、`proxy-groups`/`ProxyGroup`）
- VLESS 支持传输层：tcp / ws / grpc / h2 / quic
- VLESS 支持安全层：none / tls / reality
- 规则集自动更新（Loyalsoldier/clash-rules，每 24 小时更新）
- GitHub Actions 每 2 小时自动运行，结果上传至 Gist
- 也可在 VPS 上直接运行或远程触发 Actions

## 部署方式

本项目提供三种部署方式，按需选择：

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| **GitHub Actions** | 每 2 小时自动运行，结果上传 Gist | 推荐，零运维 |
| **VPS 直接运行** | 在 Debian 服务器上用 crontab 定时执行 | 不想依赖 GitHub |
| **VPS 远程触发 Actions** | VPS 上通过 API 触发 GitHub Actions | VPS 有定时任务，但想用 Gist 托管结果 |

---

## 方式一：GitHub Actions（推荐）

### 第 1 步：Fork 仓库

点击页面右上角的 **Fork** 按钮，将本仓库复制到你的 GitHub 账号下。

### 第 2 步：获取 GitHub Personal Access Token

Actions 运行后需要将合并结果上传到 GitHub Gist，这需要一个具有 `gist` 权限的 Token。

1. 打开 GitHub，点击右上角头像 → **Settings**
2. 左侧菜单拉到底部 → **Developer settings**
3. 左侧点击 **Personal access tokens** → **Fine-grained tokens**
4. 点击 **Generate new token**
5. 填写信息：
   - **Token name**：随意，例如 `merge_link_gist`
   - **Expiration**：按需选择（建议 90 天或 1 年）
   - **Repository access**：选择 **Only select repositories** → 选择你 Fork 的仓库
   - **Permissions** → **Account permissions** → 找到 **Gist** → 选择 **Read and write**
6. 点击 **Generate token**
7. **立即复制 Token**（页面关闭后无法再次查看）

> [!WARNING]
> Token 只会显示一次，请立即复制保存。如果丢失需要重新生成。

### 第 3 步：添加 Repository Secrets

进入你 Fork 的仓库页面：

1. 点击 **Settings** → 左侧 **Secrets and variables** → **Actions**
2. 点击 **New repository secret**，逐个添加以下 Secret：

| Name | Value | 说明 |
|------|-------|------|
| `NODE_URLS` | `https://a.com/nodes.yaml,https://b.com/nodes.yaml` | 逗号分隔的节点配置 URL 列表 |
| `VLESS_LINKS` | `vless://uuid@server:port?params#name` | 逗号分隔的 VLESS 分享链接 |
| `V2RAY_SUB_URLS` | `https://sub.example.com/sub` | 逗号分隔的 v2ray 订阅链接（返回 base64 编码的 VLESS 链接列表） |
| `GIST_TOKEN` | `github_pat_xxx...` | 第 2 步获取的 GitHub Token |
| `GIST_ID` | 留空 | 首次运行会自动创建 Gist 并输出 ID |

添加步骤（以 `NODE_URLS` 为例）：
1. 点击 **New repository secret**
2. **Name** 输入 `NODE_URLS`
3. **Secret** 输入你的节点配置 URL（多个用逗号分隔）
4. 点击 **Add secret**
5. 重复以上步骤添加其他 Secret

> [!NOTE]
> `NODE_URLS`、`VLESS_LINKS` 和 `V2RAY_SUB_URLS` 至少需要设置一个。

### 第 4 步：首次运行

1. 进入仓库的 **Actions** 页面
2. 左侧选择 **Update Clash Config**
3. 点击 **Run workflow** → **Run workflow**
4. 等待运行完成，点击进入查看日志
5. 首次运行会在日志中输出 Gist ID 和订阅 URL，格式类似：

```
Gist ID: abc123def456
Gist URL: https://gist.github.com/your-username/abc123def456
Raw URL (Clash 订阅链接): https://gist.githubusercontent.com/your-username/raw/abc123def456/clash_config.yaml
```

6. 复制 `GIST_ID` 的值，回到 **Settings → Secrets → Actions**，添加为新的 Secret（Name: `GIST_ID`，Value: 刚才输出的 ID）

> [!TIP]
> 之后每 2 小时会自动运行一次，也可以随时手动触发。`GIST_ID` 设置后，后续运行会更新同一个 Gist，订阅链接不变。

### 第 5 步：在 Clash / Mihomo 中使用

将上面获取的 Raw URL 添加为 Clash / Mihomo 的订阅链接即可。

---

## 方式二：VPS 直接运行

在 Debian / Ubuntu 服务器上直接运行合并脚本，不依赖 GitHub Actions。

### 第 1 步：克隆仓库

```bash
git clone https://github.com/你的用户名/Merge_link.git
cd Merge_link
```

### 第 2 步：设置环境变量

```bash
export NODE_URLS="https://a.com/nodes.yaml,https://b.com/nodes.yaml"
export VLESS_LINKS="vless://uuid@server:port?params#name"
export V2RAY_SUB_URLS="https://sub.example.com/sub"
```

> [!TIP]
> 可以将这些 `export` 写入 `~/.bashrc` 或 `~/.profile` 使其持久化。

### 第 3 步：运行部署脚本

```bash
bash setup_cron.sh
```

脚本会自动：
- 安装 `python3`、`pip`、`venv`
- 创建虚拟环境并安装 `pyyaml`
- 运行一次测试
- 设置 crontab 每 2 小时执行一次

输出文件为 `merged_config.yaml`，日志写入 `merge_clash.log`。

---

## 方式三：VPS 远程触发 GitHub Actions

在 VPS 上通过 GitHub API 触发 Actions 运行，适合已有 VPS 定时任务但想用 Gist 托管结果的场景。

### 第 1 步：获取 GitHub Token

按照方式一的「第 2 步」获取一个具有 `workflow` 权限的 Token（需要勾选 **Actions** → **Read and write**，以及 **Gist** → **Read and write**）。

### 第 2 步：在 VPS 上配置 Token

二选一：

**方法 A：环境变量**（推荐）

```bash
export GITHUB_TOKEN="github_pat_xxx..."
```

**方法 B：Token 文件**

将 Token 写入脚本同目录下的 `.github_token` 文件：

```bash
echo "github_pat_xxx..." > .github_token
chmod 600 .github_token
```

### 第 3 步：克隆仓库并运行

```bash
git clone https://github.com/你的用户名/Merge_link.git
cd Merge_link
chmod +x trigger_actions.sh
```

**手动触发一次：**

```bash
bash trigger_actions.sh
```

**安装定时任务（每 2 小时自动触发）：**

```bash
bash trigger_actions.sh --install
```

**查看定时任务状态：**

```bash
bash trigger_actions.sh --status
```

**移除定时任务：**

```bash
bash trigger_actions.sh --uninstall
```

日志写入 `trigger_actions.log`。

---

## 环境变量说明

| 变量 | 必需 | 说明 |
|------|------|------|
| `TEMPLATE_FILE` | 否 | 基础配置模板文件路径（默认 `config_template.yaml`） |
| `NODE_URLS` | 三选一 | 逗号分隔的节点配置 URL，每个 URL 指向一个包含 `proxies` 的 YAML |
| `VLESS_LINKS` | 三选一 | 逗号分隔的 VLESS 分享链接（`vless://uuid@server:port?params#name`） |
| `V2RAY_SUB_URLS` | 三选一 | 逗号分隔的 v2ray 订阅链接，返回 base64 编码的 VLESS 链接列表 |

## 项目结构

```
Merge_link/
├── merge_clash.py              # 核心合并脚本
├── config_template.yaml        # 基础配置模板（DNS、规则集、规则）
├── setup_cron.sh               # VPS 直接部署脚本
├── setup_vnstat.sh             # vnstat 流量统计一键部署脚本
├── trigger_actions.sh          # VPS 远程触发 Actions 脚本
├── .github/
│   └── workflows/
│       └── update-config.yml   # GitHub Actions 工作流
├── .gitignore
├── CLAUDE.md
└── README.md
```

## 工作原理

```
config_template.yaml ──→ 基础配置（DNS、规则集、规则）
                │
NODE_URLS ──→ 节点配置 ──┐
                         │
VLESS_LINKS → VLESS 解析 ─┼──→ 合并去重 ──→ 创建分组 ──→ merged_config.yaml ──→ Gist
                         │
V2RAY_SUB_URLS ──────────┘
    ↓
    base64 解码 → VLESS 链接列表 → 解析合并
```

1. 从本地 `config_template.yaml` 加载基础配置（DNS、规则集、规则）
2. 遍历 `NODE_URLS`，逐个获取并提取 `proxies` 节点 → 创建 `node-手选` / `node-自动` 分组
3. 遍历 `VLESS_LINKS`，解析为 Clash Meta 代理字典 → 创建 `vless-手选` / `vless-自动` 分组
4. 遍历 `V2RAY_SUB_URLS`，获取订阅内容并 base64 解码，解析 VLESS 链接 → 创建 `v2-手选` / `v2-自动` 分组
5. 重名节点自动添加来源后缀（`-node`、`-vless`、`-v2`）
6. 创建统一分组：`手选-azheng`（所有节点）、`自动-azheng`（自动选择延迟最低）
7. 创建负载均衡分组：`hash-node`、`hash-vless`、`hash-v2`（一致性哈希策略）
8. 构建主分组 `节点选择`，引用所有分组
9. 输出 `merged_config.yaml`，上传至 Gist

## 分组结构

```
节点选择 (主分组)
├── 手选-azheng          # 所有节点，手动选择
├── 自动-azheng          # 所有节点，自动选择延迟最低
├── hash-node            # NODE_URLS 节点，一致性哈希负载均衡
├── hash-vless           # VLESS_LINKS 节点，一致性哈希负载均衡
├── hash-v2              # V2RAY_SUB_URLS 节点，一致性哈希负载均衡
├── node-手选 / node-自动    # NODE_URLS 来源分组
├── vless-手选 / vless-自动  # VLESS_LINKS 来源分组
└── v2-手选 / v2-自动        # V2RAY_SUB_URLS 来源分组
```

## 附：vnstat 流量统计

`setup_vnstat.sh` 提供一键部署每小时流量统计功能。

### 功能

- 自动检测并安装 vnstat（支持 apt/yum/dnf/pacman）
- 自动检测网络接口
- 每小时统计流量增量和当日累计
- 日志写入 `/var/log/traffic_hourly.log`

### 使用方法

```bash
chmod +x setup_vnstat.sh
sudo ./setup_vnstat.sh
```

### 部署后

| 命令 | 说明 |
|------|------|
| `vnstat -l` | 查看实时流量 |
| `vnstat -d` | 查看今日统计 |
| `vnstat -m` | 查看本月统计 |
| `vnstat -h` | 查看小时统计 |
| `tail -f /var/log/traffic_hourly.log` | 查看日志 |

### 日志格式

```
2024-01-15 14:00 | 本小时增量: RX +12.34MB / TX +5.67MB | 当日累计: RX: 1024.00 MB (1.00 GB) | TX: 512.00 MB (0.50 GB)
```

---

## 常见问题

**Q: 只有 VLESS 链接，没有节点 URL 怎么办？**

只设置 `VLESS_LINKS` 即可，`NODE_URLS` 可以不设置或留空。

**Q: v2ray 订阅链接是什么？**

v2ray 订阅链接返回 base64 编码的 VLESS 链接列表。设置 `V2RAY_SUB_URLS` 后，脚本会自动获取、解码、解析，并创建 `v2-*` 分组存放这些节点。

**Q: Actions 运行失败怎么办？**

进入 Actions 页面查看日志，常见原因：
- 节点 URL 无法访问
- Token 权限不足（需要 `gist` 权限）
- `GIST_ID` 填写错误

**Q: 如何手动触发更新？**

- GitHub Actions：进入 Actions 页面 → Run workflow
- VPS：运行 `bash trigger_actions.sh`

**Q: 订阅链接在哪里找？**

首次运行 Actions 后在日志中查看 Raw URL。设置了 `GIST_ID` 后，链接格式为：
```
https://gist.githubusercontent.com/你的用户名/{GIST_ID}/raw/clash_config.yaml
```
