#!/usr/bin/env python3
"""
合并多个 Clash 配置文件的代理节点。
从 BASE_URL 获取基础配置（规则、代理组），
从 NODE_URLS 获取所有节点，合并后生成新文件。
兼容 Windows 和 Ubuntu。
"""

import io
import sys
import ssl
import urllib.request
import urllib.error
from pathlib import Path

# Windows 终端可能使用 GBK，强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("错误: 需要安装 PyYAML，请运行: pip install pyyaml")
    sys.exit(1)


BASE_URL = "https://app.mitce.net/?sid=481362&token=srvcmhfb&app=clashverge"
NODE_URLS = [
    "https://144.225.187.179:2096/clash/kx4aldko08futa52",
    # 在这里添加更多 NODE_URL，每行一个
]
OUTPUT_FILE = "merged_config.yaml"


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


def merge_proxies(base: dict, node_config: dict) -> None:
    """
    将 node_config 中的 proxies 合并到 base 中，
    并将新节点添加到 proxy-groups 中包含最多代理的组里。
    """
    # 提取新节点
    new_proxies = node_config.get("proxies") or node_config.get("Proxy") or []
    if not new_proxies:
        # 如果链接2本身就是单个代理节点（无 proxies 顶层键），尝试直接构造
        if "server" in node_config and "port" in node_config:
            new_proxies = [node_config]
        else:
            print("警告: 链接2中未找到任何代理节点")
            return

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
        return

    print(f"新增 {len(added)} 个节点: {', '.join(added)}")

    # 找到包含最多代理的 proxy-group
    groups = base.get("proxy-groups") or base.get("ProxyGroup") or []
    if not groups:
        print("警告: 未找到 proxy-groups，跳过组添加")
        return

    largest_group = max(groups, key=lambda g: len(g.get("proxies", [])))
    largest_group_name = largest_group.get("name", "未知")
    group_proxies = largest_group.get("proxies", [])

    # 添加新节点到该组（去重）
    for name in added:
        if name not in group_proxies:
            group_proxies.append(name)

    largest_group["proxies"] = group_proxies
    print(f"已将节点添加到最大组: {largest_group_name} (现含 {len(group_proxies)} 个代理)")


def main() -> None:
    print("=" * 50)
    print("Clash 配置合并工具")
    print("=" * 50)

    # 1. 获取基础配置
    print(f"\n[1/2] 正在获取基础配置...")
    print(f"  URL: {BASE_URL}")
    try:
        base_text = fetch_url(BASE_URL)
        base_config = parse_yaml(base_text)
        print(f"  成功，配置名: {base_config.get('name', base_config.get('mixed-port', '未知'))}")
    except Exception as e:
        print(f"  获取基础配置失败: {e}")
        sys.exit(1)

    # 2. 获取并合并所有 NODE_URL
    print(f"\n[2/2] 正在获取并合并节点...")
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
