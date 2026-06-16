# Merge_link

Clash / Mihomo 代理配置合并工具。从远程 URL 获取基础配置（规则、代理组、DNS），再从多个节点 URL、VLESS 分享链接和 v2ray 订阅链接中提取代理节点，合并输出为单一 YAML 配置文件，并可自动上传至 GitHub Gist 作为订阅链接使用。

## 功能特性

- 从远程 URL 获取基础 Clash 配置作为骨架
- 支持从多个节点 URL 合并代理节点
- 支持 VLESS 分享链接直接解析为 Clash Meta 代理节点
- 支持 v2ray 订阅链接（base64 编码的 VLESS 链接列表），自动创建 "vps" 代理组
- 自动按 name 去重，新节点自动添加到最大的 proxy-group
- 兼容 Clash 和 Mihomo 的键名格式（`proxies`/`Proxy`、`proxy-groups`/`ProxyGroup`）
- VLESS 支持传输层：tcp / ws / grpc / h2 / quic
- VLESS 支持安全层：none / tls / reality
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
| `BASE_URL` | `https://example.com/base.yaml` | 基础 Clash 配置 URL（提供规则、代理组、DNS） |
| `NODE_URLS` | `https://a.com/nodes.yaml,https://b.com/nodes.yaml` | 逗号分隔的节点配置 URL 列表 |
| `VLESS_LINKS` | `vless://uuid@server:port?params#name` | 逗号分隔的 VLESS 分享链接 |
| `V2RAY_SUB_URLS` | `https://sub.example.com/sub` | 逗号分隔的 v2ray 订阅链接（返回 base64 编码的 VLESS 链接列表） |
| `GIST_TOKEN` | `github_pat_xxx...` | 第 2 步获取的 GitHub Token |
| `GIST_ID` | 留空 | 首次运行会自动创建 Gist 并输出 ID |

添加步骤（以 `BASE_URL` 为例）：
1. 点击 **New repository secret**
2. **Name** 输入 `BASE_URL`
3. **Secret** 输入你的基础配置 URL
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
export BASE_URL="https://example.com/base.yaml"
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
| `BASE_URL` | 是 | 基础 Clash 配置 URL，提供规则、代理组、DNS 等骨架 |
| `NODE_URLS` | 三选一 | 逗号分隔的节点配置 URL，每个 URL 指向一个包含 `proxies` 的 YAML |
| `VLESS_LINKS` | 三选一 | 逗号分隔的 VLESS 分享链接（`vless://uuid@server:port?params#name`） |
| `V2RAY_SUB_URLS` | 三选一 | 逗号分隔的 v2ray 订阅链接，返回 base64 编码的 VLESS 链接列表，自动创建 "vps" 代理组 |

## 项目结构

```
Merge_link/
├── merge_clash.py              # 核心合并脚本
├── setup_cron.sh               # VPS 直接部署脚本
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
BASE_URL ──→ 基础配置（规则、代理组、DNS）
                │
NODE_URLS ──→ 节点配置 ──┐
                         │
VLESS_LINKS → VLESS 解析 ─┼──→ 合并去重 ──→ merged_config.yaml ──→ Gist（订阅链接）
                         │
V2RAY_SUB_URLS ──────────┘
    ↓
    base64 解码 → VLESS 链接列表 → 解析合并
    同时创建 "vps" 代理组
```

1. 从 `BASE_URL` 获取基础配置作为骨架
2. 遍历 `NODE_URLS`，逐个获取并提取 `proxies` 节点
3. 遍历 `VLESS_LINKS`，解析为 Clash Meta 代理字典
4. 遍历 `V2RAY_SUB_URLS`，获取订阅内容并 base64 解码，解析 VLESS 链接，创建 "vps" 代理组
5. 按 `name` 去重，新节点添加到最大的 `proxy-group`
6. 输出 `merged_config.yaml`，上传至 Gist

## 常见问题

**Q: 只有 VLESS 链接，没有节点 URL 怎么办？**

只设置 `VLESS_LINKS` 即可，`NODE_URLS` 可以不设置或留空。

**Q: v2ray 订阅链接是什么？**

v2ray 订阅链接返回 base64 编码的 VLESS 链接列表。设置 `V2RAY_SUB_URLS` 后，脚本会自动获取、解码、解析，并创建一个名为 "vps" 的代理组存放这些节点。

**Q: Actions 运行失败怎么办？**

进入 Actions 页面查看日志，常见原因：
- `BASE_URL` 无法访问
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
