#!/usr/bin/env python3
"""
合并多个 Clash 配置文件的代理节点。
从本地模板读取基础配置（DNS、规则、规则集），
从 NODE_URLS、VLESS_LINKS、V2RAY_SUB_URLS 获取节点，
按来源生成手选 + 自动选择分组，合并后输出。
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
TEMPLATE_FILE = os.environ.get("TEMPLATE_FILE", "config_template.yaml")
NODE_URLS = [url.strip() for url in os.environ.get("NODE_URLS", "").split(",") if url.strip()]
VLESS_LINKS = [link.strip() for link in os.environ.get("VLESS_LINKS", "").split(",") if link.strip()]
V2RAY_SUB_URLS = [url.strip() for url in os.environ.get("V2RAY_SUB_URLS", "").split(",") if url.strip()]
OUTPUT_FILE = "merged_config.yaml"

# 如果没有任何来源，提示用户设置
if not NODE_URLS and not VLESS_LINKS and not V2RAY_SUB_URLS:
    print("错误: 请设置 NODE_URLS、VLESS_LINKS 或 V2RAY_SUB_URLS 环境变量（至少一个）")
    sys.exit(1)


def load_template(path: str) -> dict:
    """从本地文件加载模板配置。"""
    template_path = Path(path)
    if not template_path.exists():
        print(f"错误: 模板文件不存在: {template_path.resolve()}")
        sys.exit(1)
    with open(template_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("模板文件不是有效的字典结构")
    return data


def read_source(path_or_url: str) -> str:
    """读取来源内容：本地文件路径直接读取，URL 通过 HTTP 获取。"""
    # 判断是否为本地文件路径（不以 http:// 或 https:// 开头）
    if not path_or_url.startswith(("http://", "https://")):
        file_path = Path(path_or_url)
        if not file_path.exists():
            raise FileNotFoundError(f"本地文件不存在: {file_path.resolve()}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return fetch_url(path_or_url)


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


def deduplicate_name(name: str, source_type: str, existing_names: set) -> str:
    """
    为重名节点自动添加编号后缀：-01, -02, -03, ...
    第一个重名加 -01，第二个加 -02，依此类推。
    """
    counter = 1
    while True:
        new_name = f"{name}-{counter:02d}"
        if new_name not in existing_names:
            return new_name
        counter += 1


def merge_proxies(base: dict, node_config: dict, source_type: str = "node") -> tuple:
    """
    将 node_config 中的 proxies 合并到 base 中（按 name 去重）。
    返回 (新增的节点名称列表, 重名映射 {旧名: 新名})。
    """
    new_proxies = node_config.get("proxies") or node_config.get("Proxy") or []
    if not new_proxies:
        if "server" in node_config and "port" in node_config:
            new_proxies = [node_config]
        else:
            print("警告: 链接中未找到任何代理节点")
            return [], {}

    base_proxies = base.get("proxies") or base.get("Proxy") or []
    existing_names = {p.get("name") for p in base_proxies}

    added = []
    name_map = {}  # 重名节点的旧名 → 新名映射
    for proxy in new_proxies:
        name = proxy.get("name", "")
        if name in existing_names:
            # 根据来源类型添加后缀，而不是跳过
            new_name = deduplicate_name(name, source_type, existing_names)
            proxy["name"] = new_name
            print(f"  重名节点已重命名: {name} → {new_name}")
            name_map[name] = new_name
            name = new_name
        base_proxies.append(proxy)
        existing_names.add(name)
        added.append(name)

    if "proxies" in base:
        base["proxies"] = base_proxies
    elif "Proxy" in base:
        base["Proxy"] = base_proxies
    else:
        base["proxies"] = base_proxies

    if not added:
        print("没有新节点需要添加")
    else:
        print(f"新增 {len(added)} 个节点: {', '.join(added)}")

    return added, name_map


def fetch_v2ray_sub(url: str) -> list:
    """
    获取 v2ray 订阅链接内容，解码 base64，返回 vless:// 链接列表。
    """
    print(f"  正在获取订阅内容...")
    content = fetch_url(url)

    try:
        padding = 4 - len(content) % 4
        if padding != 4:
            content += "=" * padding
        decoded = base64.b64decode(content).decode("utf-8")
    except Exception:
        decoded = content

    links = [line.strip() for line in decoded.splitlines() if line.strip()]
    vless_links = [link for link in links if link.startswith("vless://")]
    print(f"  解析到 {len(vless_links)} 个 VLESS 链接")
    return vless_links


def create_source_groups(base: dict, source_name: str, proxy_names: list) -> str:
    """
    为一个来源创建手选 + 自动选择两个代理组。
    返回主分组中需要引用的组名前缀。
    """
    if not proxy_names:
        return ""

    groups = base.get("proxy-groups") or base.get("ProxyGroup") or []

    # 手选组
    select_name = f"{source_name}-手选"
    groups.append({
        "name": select_name,
        "type": "select",
        "proxies": list(proxy_names),
    })

    # 自动选择组（url-test）
    auto_name = f"{source_name}-自动"
    groups.append({
        "name": auto_name,
        "type": "url-test",
        "url": "http://www.gstatic.com/generate_204",
        "interval": 300,
        "tolerance": 30,
        "proxies": list(proxy_names),
    })

    print(f"  已创建分组: {select_name} / {auto_name} (含 {len(proxy_names)} 个节点)")

    if "proxy-groups" in base:
        base["proxy-groups"] = groups
    elif "ProxyGroup" in base:
        base["ProxyGroup"] = groups
    else:
        base["proxy-groups"] = groups

    return source_name


def merge_remote_proxy_groups(base: dict, remote_groups: list, name_map: dict) -> list:
    """
    将远程配置自带的 proxy-groups 合并到 base 中。
    - 所有远程分组统一添加 "node-" 前缀，避免与脚本分组（node-手选等）和模板分组冲突。
    - name_map: 重名节点的 {旧名: 新名} 映射，用于修正分组内的 proxies 引用。
    - 多个远程配置有同名分组时，后续加编号去重。
    返回实际合并的分组名称列表。
    """
    if not remote_groups:
        return []

    base_groups = base.get("proxy-groups") or base.get("ProxyGroup") or []
    existing_names = {g.get("name") for g in base_groups}

    # 第一遍：确定所有远程分组的新名字，构建分组名映射
    group_remap = {}  # 远程分组原始名 → 新名
    for group in remote_groups:
        old_name = group.get("name", "")
        if not old_name:
            continue
        new_name = f"node-{old_name}"
        counter = 2
        while new_name in existing_names:
            new_name = f"node-{old_name}-{counter}"
            counter += 1
        group_remap[old_name] = new_name
        existing_names.add(new_name)

    # 合并节点重名映射和分组名映射，用于统一修正 proxies 引用
    full_remap = {}
    if name_map:
        full_remap.update(name_map)
    full_remap.update(group_remap)

    # 第二遍：重命名分组 + 修正所有 proxies 引用
    added_names = []
    for group in remote_groups:
        old_name = group.get("name", "")
        if not old_name:
            continue

        new_name = group_remap[old_name]
        if new_name != f"node-{old_name}":
            print(f"  远程分组重名已重命名: {old_name} → {new_name}")
        group["name"] = new_name

        # 修正 proxies 引用（节点名 + 分组名）
        if full_remap and "proxies" in group:
            group["proxies"] = [
                full_remap.get(p, p) for p in group["proxies"]
            ]

        base_groups.append(group)
        added_names.append(new_name)

    if added_names:
        print(f"  已合并远程分组: {', '.join(added_names)}")

    if "proxy-groups" in base:
        base["proxy-groups"] = base_groups
    elif "ProxyGroup" in base:
        base["ProxyGroup"] = base_groups
    else:
        base["proxy-groups"] = base_groups

    return added_names


def create_unified_groups(base: dict, all_proxy_names: list, hash_names: list = None, auto_names: list = None) -> None:
    """
    创建统一的手选-azheng 和自动-azheng 分组，包含所有来源的节点。
    手选-azheng 额外包含 hash 分组和自动分组，方便手动切换使用。
    """
    if not all_proxy_names:
        return

    groups = base.get("proxy-groups") or base.get("ProxyGroup") or []

    # 手选-azheng（手动选择所有节点 + hash 分组 + 自动分组）
    select_proxies = list(all_proxy_names) + (hash_names or []) + (auto_names or [])
    groups.append({
        "name": "手选-azheng",
        "type": "select",
        "proxies": select_proxies,
    })

    # 自动-azheng（自动选择延迟最低的节点）
    groups.append({
        "name": "自动-azheng",
        "type": "url-test",
        "url": "http://www.gstatic.com/generate_204",
        "interval": 300,
        "tolerance": 30,
        "proxies": list(all_proxy_names),
    })

    print(f"  已创建统一分组: 手选-azheng ({len(select_proxies)} 个选项) / 自动-azheng ({len(all_proxy_names)} 个节点)")

    if "proxy-groups" in base:
        base["proxy-groups"] = groups
    elif "ProxyGroup" in base:
        base["ProxyGroup"] = groups
    else:
        base["proxy-groups"] = groups


def create_hash_groups(base: dict, source_proxy_map: dict) -> list:
    """
    为每个来源类型创建 load-balance（一致性哈希）分组。
    source_proxy_map: {"node": [...], "vless": [...], "v2": [...]}
    返回创建的 hash 分组名称列表。
    """
    if not source_proxy_map:
        return []

    groups = base.get("proxy-groups") or base.get("ProxyGroup") or []
    hash_names = []

    for source_type, proxy_names in source_proxy_map.items():
        if not proxy_names:
            continue

        hash_name = f"hash-{source_type}"
        groups.append({
            "name": hash_name,
            "type": "load-balance",
            "url": "http://www.gstatic.com/generate_204",
            "interval": 180,
            "strategy": "consistent-hashing",
            "proxies": list(proxy_names),
        })
        hash_names.append(hash_name)
        print(f"  已创建 hash 分组: {hash_name} (含 {len(proxy_names)} 个节点)")

    if "proxy-groups" in base:
        base["proxy-groups"] = groups
    elif "ProxyGroup" in base:
        base["ProxyGroup"] = groups
    else:
        base["proxy-groups"] = groups

    return hash_names


def build_main_group(base: dict, source_names: list, hash_names: list = None, extra_groups: list = None) -> None:
    """
    构建"节点选择"主分组，包含 DIRECT、REJECT 和所有来源的手选/自动组。
    extra_groups: 额外要加入主分组的组名列表（如远程配置自带的分组）。
    """
    if not source_names:
        return

    groups = base.get("proxy-groups") or base.get("ProxyGroup") or []

    main_proxies = ["DIRECT", "REJECT", "手选-azheng", "自动-azheng"]
    for name in source_names:
        main_proxies.append(f"{name}-手选")
        main_proxies.append(f"{name}-自动")

    # 添加 hash 分组
    if hash_names:
        for name in hash_names:
            main_proxies.append(name)

    # 添加远程配置自带的分组
    if extra_groups:
        for name in extra_groups:
            main_proxies.append(name)

    # 移除已有的"节点选择"组（如果模板中存在）
    groups = [g for g in groups if g.get("name") != "节点选择"]

    # 插入到最前面
    groups.insert(0, {
        "name": "节点选择",
        "type": "select",
        "proxies": main_proxies,
    })

    if "proxy-groups" in base:
        base["proxy-groups"] = groups
    elif "ProxyGroup" in base:
        base["ProxyGroup"] = groups
    else:
        base["proxy-groups"] = groups

    print(f"  已创建主分组: 节点选择 (含 {len(main_proxies)} 个选项)")


def main() -> None:
    print("=" * 50)
    print("Clash 配置合并工具")
    print("=" * 50)

    # 1. 加载本地模板
    print(f"\n[1/4] 正在加载模板配置...")
    print(f"  文件: {Path(TEMPLATE_FILE).resolve()}")
    try:
        base_config = load_template(TEMPLATE_FILE)
        print(f"  成功加载模板")
    except Exception as e:
        print(f"  加载模板失败: {e}")
        sys.exit(1)

    source_names = []
    all_proxy_names = []  # 收集所有节点名称，用于创建统一分组
    source_proxy_map = {}  # 按来源类型收集节点名称，用于创建 hash 分组
    auto_names = []  # 收集自动分组名称，加入手选-azheng
    remote_group_names = []  # 收集远程配置自带的分组名称

    # 2. 获取并合并所有 NODE_URL
    if NODE_URLS:
        print(f"\n[2/4] 正在获取并合并节点链接...")
        all_added = []
        all_name_map = {}  # 收集所有重名映射
        all_remote_groups = []  # 收集所有远程配置自带的分组
        for i, node_url in enumerate(NODE_URLS, 1):
            print(f"\n  [{i}/{len(NODE_URLS)}] 来源: {node_url}")
            try:
                node_text = read_source(node_url)
                node_config = parse_yaml(node_text)
                node_count = len(node_config.get("proxies", node_config.get("Proxy", [])))
                print(f"    获取到 {node_count} 个节点" if node_count else "    单节点配置")
                added, name_map = merge_proxies(base_config, node_config, source_type="node")
                all_added.extend(added)
                all_name_map.update(name_map)
                # 收集远程配置自带的 proxy-groups
                remote_groups = node_config.get("proxy-groups") or node_config.get("ProxyGroup") or []
                if remote_groups:
                    print(f"    发现 {len(remote_groups)} 个远程分组")
                    all_remote_groups.extend(remote_groups)
            except Exception as e:
                print(f"    获取失败: {e}，跳过")
                continue
        if all_added:
            create_source_groups(base_config, "node", all_added)
            source_names.append("node")
            all_proxy_names.extend(all_added)
            source_proxy_map["node"] = all_added
            auto_names.append("node-自动")
            # 合并远程配置自带的分组
            if all_remote_groups:
                remote_group_names = merge_remote_proxy_groups(base_config, all_remote_groups, all_name_map)

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
            added, _ = merge_proxies(base_config, {"proxies": vless_proxies}, source_type="vless")
            if added:
                create_source_groups(base_config, "vless", added)
                source_names.append("vless")
                all_proxy_names.extend(added)
                source_proxy_map["vless"] = added
                auto_names.append("vless-自动")

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
            added, _ = merge_proxies(base_config, {"proxies": v2ray_proxies}, source_type="v2")
            if added:
                create_source_groups(base_config, "v2", added)
                source_names.append("v2")
                all_proxy_names.extend(added)
                source_proxy_map["v2"] = added
                auto_names.append("v2-自动")

    # 5. 创建 hash 分组、统一分组和主分组
    print(f"\n[构建分组]")
    hash_names = create_hash_groups(base_config, source_proxy_map)
    create_unified_groups(base_config, all_proxy_names, hash_names, auto_names)
    build_main_group(base_config, source_names, hash_names, remote_group_names)

    # 输出统计
    final_proxies = base_config.get("proxies", base_config.get("Proxy", []))
    final_groups = base_config.get("proxy-groups", base_config.get("ProxyGroup", []))
    print(f"\n最终统计:")
    print(f"  代理节点总数: {len(final_proxies)}")
    print(f"  代理组总数:   {len(final_groups)}")
    for g in final_groups:
        name = g.get("name", "?")
        gtype = g.get("type", "?")
        count = len(g.get("proxies", []))
        print(f"    - {name} ({gtype}): {count} 个")

    # 写入文件
    output_path = Path(OUTPUT_FILE)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(base_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\n[OK] 已生成合并配置: {output_path.resolve()}")


if __name__ == "__main__":
    main()
