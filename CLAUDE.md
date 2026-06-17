# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Merge_link 是一个 Clash/Mihomo 代理配置合并工具。从本地模板读取基础配置（规则、DNS、规则集），再从多个节点 URL、VLESS 分享链接和 v2ray 订阅链接中提取代理节点，按来源生成手选 + 自动选择分组，合并输出为单一 YAML 配置文件。

## 运行方式

唯一依赖：`pyyaml`

```bash
pip install pyyaml
```

通过环境变量配置，直接运行脚本：

```bash
NODE_URLS="https://a.com/nodes.yaml,https://b.com/nodes.yaml" \
VLESS_LINKS="vless://uuid@server:port?params#name" \
V2RAY_SUB_URLS="https://sub.example.com/sub" \
python merge_clash.py
```

环境变量：
- `TEMPLATE_FILE` — 基础配置模板文件路径（默认 `config_template.yaml`，提供 DNS、规则、规则集）
- `NODE_URLS` — 逗号分隔的节点配置 URL 列表
- `VLESS_LINKS` — 逗号分隔的 VLESS 分享链接
- `V2RAY_SUB_URLS` — 逗号分隔的 v2ray 订阅链接（返回 base64 编码的 VLESS 链接列表）

至少需要设置 `NODE_URLS`、`VLESS_LINKS` 或 `V2RAY_SUB_URLS` 之一。输出文件为 `merged_config.yaml`。

## 架构

- `config_template.yaml` — 基础配置模板，包含 DNS、规则集、规则，不含代理节点和分组
- `merge_clash.py` — 合并脚本（约 400 行），仅依赖 stdlib + pyyaml

核心流程 `main()`：
1. `load_template(TEMPLATE_FILE)` 加载本地模板配置
2. 遍历 `NODE_URLS`，逐个获取并调用 `merge_proxies()` 合并节点 → 创建 "机场节点-手选" / "机场节点-自动" 分组
3. 遍历 `VLESS_LINKS`，`parse_vless_uri()` 解析后合并 → 创建 "直连节点-手选" / "直连节点-自动" 分组
4. 遍历 `V2RAY_SUB_URLS`，`fetch_v2ray_sub()` 解码后合并 → 创建 "订阅节点-手选" / "订阅节点-自动" 分组
5. `build_main_group()` 构建 "节点选择" 主分组，引用所有来源的手选/自动组
6. 写入 `merged_config.yaml`

关键函数：
- `load_template(path)` — 从本地文件加载模板配置
- `parse_vless_uri(uri)` — VLESS 链接解析，支持传输层 tcp/ws/grpc/h2/quic，安全层 none/tls/reality
- `merge_proxies(base, node_config)` — 按 name 去重合并 proxies，返回新增节点名称列表
- `fetch_v2ray_sub(url)` — 获取 v2ray 订阅内容，base64 解码后返回 VLESS 链接列表
- `create_source_groups(base, source_name, proxy_names)` — 为来源创建手选 + 自动选择两个分组
- `build_main_group(base, source_names)` — 构建 "节点选择" 主分组

## 兼容性细节

- 同时支持 Clash 和 Mihomo 的键名：`proxies`/`Proxy`、`proxy-groups`/`ProxyGroup`
- SSL 验证已禁用（`ssl.CERT_NONE`），适配自签证书场景
- Windows 下强制 UTF-8 stdout/stderr，避免 GBK 编码问题
- User-Agent 伪装为 `ClashForAndroid/2.5.12`

## 部署

### GitHub Actions（`.github/workflows/update-config.yml`）

每 2 小时自动运行，支持手动触发。通过 GitHub Secrets 管理环境变量（`NODE_URLS`、`VLESS_LINKS`、`V2RAY_SUB_URLS`、`GIST_TOKEN`、`GIST_ID`）。模板文件 `config_template.yaml` 随仓库提交。运行后将 `merged_config.yaml` 上传至 GitHub Gist，Gist raw URL 作为 Clash 订阅链接使用。

### Debian Cron（`setup_cron.sh`）

创建 venv、安装 pyyaml、设置 crontab 每 2 小时运行，日志写入 `merge_clash.log`。

## Git 注意事项

`merged_config.yaml`、`node_url.yaml`、`merge_clash.log` 均已 gitignore。这些文件包含代理 UUID、服务器 IP 等敏感信息，不应提交。
