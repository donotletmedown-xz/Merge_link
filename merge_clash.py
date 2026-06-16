#!/usr/bin/env python3
"""
合并多个 Clash 配置文件的代理节点。
从 BASE_URL 获取基础配置（规则、代理组），
从 NODE_URLS 获取所有节点，合并后生成新文件。
支持 VLESS 分享链接自动转换。
兼容 Windows 和 Ubuntu。
"""

import io
import os
import sys
import ssl
import base64
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

# Windows 终端可能使用 GBK，强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("错误: 需要安装 PyYAML，请运行: pip install pyyaml")
    sys.exit(1)


# 优先从环境变量读取，否则使用默认值
BASE_URL = os.environ.get("BASE_URL", "")
NODE_URLS = [url.strip() for url in os.environ.get("NODE_URLS", "").split(",") if url.strip()]
VLESS_LINKS = [link.strip() for link in os.environ.get("VLESS_LINKS", "").split(",") if link.strip()]
V2RAY_SUB_URLS = [url.strip() for url in os.environ.get("V2RAY_SUB_URLS", "").split(",") if url.strip()]
OUTPUT_FILE = "merged_config.yaml"

# 如果环境变量为空，提示用户设置
if not BASE_URL:
    print("错误: 请设置 BASE_URL 环境变量")
    sys.exit(1)
if not NODE_URLS and not VLESS_LINKS and not V2RAY_SUB_URLS:
    print("错误: 请设置 NODE_URLS、VLESS_LINKS 或 V2RAY_SUB_URLS 环境变量（至少一个）")
    sys.exit(1)


def fetch_url(url: str) -> str:
    """获取 URL 内容，跳过 SSL 验证（某些自签证书场景）。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={"User-Agent": "ClashForAndroid/2.5.12"})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        return resp.read().decode("utf-8")


def parse_yaml(text: str) -> dict:
    """解析 YAML 文本，返回字典。"""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("YAML 内容不是有效的字典结构")
    return data


def parse_vless_uri(uri: str) -> dict:
    """
    将 VLESS 分享链接解析为 Clash Meta 代理配置字典。

    支持格式: vless://UUID@SERVER:PORT?params#NAME
    支持传输: tcp / ws / grpc / h2 / quic
    支持安全: none / tls / reality
    """
    # 分离 fragment（节点名）
    if "#" in uri:
        uri_part, name = uri.rsplit("#", 1)
        name = unquote(name)
    else:
        uri_part = uri
        name = "vless-node"

    parsed = urlparse(uri_part)
    uuid = parsed.username or ""
    server = parsed.hostname or ""
    port = parsed.port or 443

    if not uuid or not server:
        raise ValueError(f"无效的 VLESS 链接，缺少 UUID 或服务器地址: {uri[:80]}...")

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    # 基础配置
    proxy = {
        "name": name,
        "type": "vless",
        "server": server,
        "port": port,
        "uuid": uuid,
        "udp": True,
    }

    # 传输层类型
    transport = params.get("type", "tcp")

    # 安全层
    security = params.get("security", "none")

    if security == "reality":
        proxy["tls"] = True
        proxy["skip-cert-verify"] = False
        if params.get("sni"):
            proxy["servername"] = params["sni"]
        if params.get("fp"):
            proxy["client-fingerprint"] = params["fp"]
        reality_opts = {}
        if params.get("pbk"):
            reality_opts["public-key"] = params["pbk"]
        if params.get("sid"):
            reality_opts["short-id"] = params["sid"]
        if reality_opts:
            proxy["reality-opts"] = reality_opts
        if params.get("flow"):
            proxy["flow"] = params["flow"]

    elif security == "tls":
        proxy["tls"] = True
        proxy["skip-cert-verify"] = params.get("allowInsecure", "0") == "1"
        if params.get("sni"):
            proxy["servername"] = params["sni"]
        elif params.get("host"):
            proxy["servername"] = params["host"]
        if params.get("fp"):
            proxy["client-fingerprint"] = params["fp"]
        if params.get("alpn"):
            proxy["alpn"] = params["alpn"].split(",")

    # 传输层配置
    if transport != "tcp":
        proxy["network"] = transport

    if transport == "ws":
        ws_opts = {}
        if params.get("path"):
            ws_opts["path"] = unquote(params["path"])
        host = params.get("host", "")
        if host:
            ws_opts["headers"] = {"Host": unquote(host)}
        if ws_opts:
            proxy["ws-opts"] = ws_opts

    elif transport == "grpc":
        if params.get("serviceName"):
            proxy["grpc-opts"] = {"grpc-service-name": params["serviceName"]}

    elif transport == "h2":
        h2_opts = {}
        if params.get("path"):
            h2_opts["path"] = unquote(params["path"])
        if params.get("host"):
            h2_opts["host"] = [unquote(params["host"])]
        if h2_opts:
            proxy["h2-opts"] = h2_opts

    return proxy


def merge_proxies(base: dict, node_config: dict, add_to_largest_group: bool = True) -> list:
    """
    将 node_config 中的 proxies 合并到 base 中。
    如果 add_to_largest_group 为 True，则将新节点添加到 proxy-groups 中包含最多代理的组里。
    返回新增的节点名称列表。
    """
    # 提取新节点
    new_proxies = node_config.get("proxies") or node_config.get("Proxy") or []
    if not new_proxies:
        # 如果链接2本身就是单个代理节点（无 proxies 顶层键），尝试直接构造
        if "server" in node_config and "port" in node_config:
            new_proxies = [node_config]
        else:
            print("警告: 链接中未找到任何代理节点")
            return []

    # 合并 proxies
    base_proxies = base.get("proxies") or base.get("Proxy") or []
    existing_names = {p.get("name") for p in base_proxies}

    added = []
    for proxy in new_proxies:
        name = proxy.get("name", "")
        if name in existing_names:
            print(f"  跳过重复节点: {name}")
            continue
        base_proxies.append(proxy)
        existing_names.add(name)
        added.append(name)

    # 确保写回正确的键
    if "proxies" in base:
        base["proxies"] = base_proxies
    elif "Proxy" in base:
        base["Proxy"] = base_proxies
    else:
        base["proxies"] = base_proxies

    if not added:
        print("没有新节点需要添加")
        return []

    print(f"新增 {len(added)} 个节点: {', '.join(added)}")

    if add_to_largest_group:
        # 找到包含最多代理的 proxy-group
        groups = base.get("proxy-groups") or base.get("ProxyGroup") or []
        if not groups:
            print("警告: 未找到 proxy-groups，跳过组添加")
            return added

        largest_group = max(groups, key=lambda g: len(g.get("proxies", [])))
        largest_group_name = largest_group.get("name", "未知")
        group_proxies = largest_group.get("proxies", [])

        # 添加新节点到该组（去重）
        for name in added:
            if name not in group_proxies:
                group_proxies.append(name)

        largest_group["proxies"] = group_proxies
        print(f"已将节点添加到最大组: {largest_group_name} (现含 {len(group_proxies)} 个代理)")

    return added


def fetch_v2ray_sub(url: str) -> list:
    """
    获取 v2ray 订阅链接内容，解码 base64，返回 vless:// 链接列表。
    """
    print(f"  正在获取订阅内容...")
    content = fetch_url(url)

    # 尝试 base64 解码
    try:
        # 添加必要的 padding
        padding = 4 - len(content) % 4
        if padding != 4:
            content += "=" * padding
        decoded = base64.b64decode(content).decode("utf-8")
    except Exception:
        # 如果解码失败，尝试直接按行分割
        decoded = content

    # 按行分割，过滤空行
    links = [line.strip() for line in decoded.splitlines() if line.strip()]

    # 只保留 vless:// 链接
    vless_links = [link for link in links if link.startswith("vless://")]
    print(f"  解析到 {len(vless_links)} 个 VLESS 链接")
    return vless_links


def create_vps_group(base: dict, proxy_names: list) -> None:
    """
    在配置中创建一个名为 "vps" 的代理组，包含指定的代理节点。
    """
    if not proxy_names:
        return

    groups = base.get("proxy-groups") or base.get("ProxyGroup") or []

    # 检查是否已存在 vps 组
    vps_group = None
    for group in groups:
        if group.get("name") == "vps":
            vps_group = group
            break

    if vps_group:
        # 已存在，合并节点
        existing = vps_group.get("proxies", [])
        for name in proxy_names:
            if name not in existing:
                existing.append(name)
        vps_group["proxies"] = existing
        print(f"已更新 vps 组 (现含 {len(existing)} 个代理)")
    else:
        # 不存在，创建新组
        new_group = {
            "name": "vps",
            "type": "select",
            "proxies": proxy_names
        }
        groups.append(new_group)
        print(f"已创建 vps 组 (含 {len(proxy_names)} 个代理)")

    # 确保写回正确的键
    if "proxy-groups" in base:
        base["proxy-groups"] = groups
    elif "ProxyGroup" in base:
        base["ProxyGroup"] = groups
    else:
        base["proxy-groups"] = groups


def main() -> None:
    print("=" * 50)
    print("Clash 配置合并工具")
    print("=" * 50)

    # 1. 获取基础配置
    print(f"\n[1/4] 正在获取基础配置...")
    print(f"  URL: {BASE_URL}")
    try:
        base_text = fetch_url(BASE_URL)
        base_config = parse_yaml(base_text)
        print(f"  成功，配置名: {base_config.get('name', base_config.get('mixed-port', '未知'))}")
    except Exception as e:
        print(f"  获取基础配置失败: {e}")
        sys.exit(1)

    # 2. 获取并合并所有 NODE_URL
    if NODE_URLS:
        print(f"\n[2/4] 正在获取并合并节点链接...")
        for i, node_url in enumerate(NODE_URLS, 1):
            print(f"\n  [{i}/{len(NODE_URLS)}] URL: {node_url}")
            try:
                node_text = fetch_url(node_url)
                node_config = parse_yaml(node_text)
                node_count = len(node_config.get("proxies", node_config.get("Proxy", [])))
                print(f"    获取到 {node_count} 个节点" if node_count else "    单节点配置")
                merge_proxies(base_config, node_config)
            except Exception as e:
                print(f"    获取失败: {e}，跳过")
                continue

    # 3. 解析并合并 VLESS 分享链接
    if VLESS_LINKS:
        print(f"\n[3/4] 正在解析 VLESS 分享链接...")
        vless_proxies = []
        for i, link in enumerate(VLESS_LINKS, 1):
            print(f"\n  [{i}/{len(VLESS_LINKS)}] {link[:60]}...")
            try:
                proxy = parse_vless_uri(link)
                vless_proxies.append(proxy)
                print(f"    ✓ {proxy['name']} → {proxy['server']}:{proxy['port']}")
            except Exception as e:
                print(f"    ✗ 解析失败: {e}")
                continue
        if vless_proxies:
            merge_proxies(base_config, {"proxies": vless_proxies})

    # 4. 获取并合并 v2ray 订阅链接
    if V2RAY_SUB_URLS:
        print(f"\n[4/4] 正在获取 v2ray 订阅链接...")
        v2ray_proxies = []
        for i, sub_url in enumerate(V2RAY_SUB_URLS, 1):
            print(f"\n  [{i}/{len(V2RAY_SUB_URLS)}] URL: {sub_url}")
            try:
                vless_links = fetch_v2ray_sub(sub_url)
                for j, link in enumerate(vless_links, 1):
                    try:
                        proxy = parse_vless_uri(link)
                        v2ray_proxies.append(proxy)
                        print(f"    [{j}/{len(vless_links)}] ✓ {proxy['name']} → {proxy['server']}:{proxy['port']}")
                    except Exception as e:
                        print(f"    [{j}/{len(vless_links)}] ✗ 解析失败: {e}")
                        continue
            except Exception as e:
                print(f"    获取订阅失败: {e}，跳过")
                continue

        if v2ray_proxies:
            # 先添加到最大组（不创建 vps 组）
            added_names = merge_proxies(base_config, {"proxies": v2ray_proxies}, add_to_largest_group=True)
            # 创建 vps 组
            if added_names:
                create_vps_group(base_config, added_names)

    # 输出统计
    final_proxies = base_config.get("proxies", base_config.get("Proxy", []))
    final_groups = base_config.get("proxy-groups", base_config.get("ProxyGroup", []))
    print(f"\n最终统计:")
    print(f"  代理节点总数: {len(final_proxies)}")
    print(f"  代理组总数:   {len(final_groups)}")

    # 写入文件
    output_path = Path(OUTPUT_FILE)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(base_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\n[OK] 已生成合并配置: {output_path.resolve()}")


if __name__ == "__main__":
    main()
