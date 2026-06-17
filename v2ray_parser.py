#!/usr/bin/env python3
"""
v2ray 订阅链接解析工具
支持解析 base64 编码的订阅内容，提取 VLESS 节点信息。
可从 URL 获取或直接解析 base64 内容。
"""

import io
import sys
import ssl
import json
import base64
import urllib.request
from urllib.parse import urlparse, parse_qs, unquote

# Windows 终端 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def fetch_url(url: str) -> str:
    """获取 URL 内容，跳过 SSL 验证。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={
        "User-Agent": "ClashForAndroid/2.5.12"
    })
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        return resp.read().decode("utf-8")


def decode_base64(content: str) -> str:
    """Base64 解码，自动处理 padding。"""
    # 移除空白字符
    content = content.strip()

    # 补齐 padding
    padding = 4 - len(content) % 4
    if padding != 4:
        content += "=" * padding

    try:
        return base64.b64decode(content).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Base64 解码失败: {e}")


def parse_vless_uri(uri: str) -> dict:
    """
    解析 VLESS 分享链接为结构化数据。

    格式: vless://UUID@SERVER:PORT?params#NAME

    返回字典包含:
    - name: 节点名称
    - server: 服务器地址
    - port: 端口
    - uuid: UUID
    - transport: 传输层类型 (tcp/ws/grpc/h2/quic)
    - security: 安全类型 (none/tls/reality)
    - tls: TLS 配置
    - transport_config: 传输层配置
    - raw: 原始链接
    """
    raw_uri = uri

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
        raise ValueError(f"无效的 VLESS 链接，缺少 UUID 或服务器地址")

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    # 传输层类型
    transport = params.get("type", "tcp")

    # 安全层
    security = params.get("security", "none")

    # 构建结果
    result = {
        "name": name,
        "server": server,
        "port": port,
        "uuid": uuid,
        "transport": transport,
        "security": security,
        "tls": {},
        "transport_config": {},
        "raw": raw_uri
    }

    # TLS 配置
    if security == "reality":
        result["tls"] = {
            "enabled": True,
            "reality": True,
            "sni": params.get("sni", ""),
            "fingerprint": params.get("fp", ""),
            "public_key": params.get("pbk", ""),
            "short_id": params.get("sid", ""),
            "flow": params.get("flow", "")
        }
    elif security == "tls":
        result["tls"] = {
            "enabled": True,
            "reality": False,
            "sni": params.get("sni", params.get("host", "")),
            "fingerprint": params.get("fp", ""),
            "alpn": params.get("alpn", "").split(",") if params.get("alpn") else [],
            "allow_insecure": params.get("allowInsecure", "0") == "1"
        }
    else:
        result["tls"] = {"enabled": False}

    # 传输层配置
    if transport == "ws":
        result["transport_config"] = {
            "path": unquote(params.get("path", "/")),
            "host": unquote(params.get("host", ""))
        }
    elif transport == "grpc":
        result["transport_config"] = {
            "service_name": params.get("serviceName", "")
        }
    elif transport == "h2":
        result["transport_config"] = {
            "path": unquote(params.get("path", "/")),
            "host": [unquote(params.get("host", ""))]
        }

    return result


def parse_subscription(content: str) -> list:
    """
    解析订阅内容，返回节点列表。
    自动处理 base64 解码和链接分割。
    """
    # 尝试 base64 解码
    try:
        decoded = decode_base64(content)
    except ValueError:
        # 如果解码失败，假设已经是纯文本
        decoded = content

    # 按行分割，过滤空行
    lines = [line.strip() for line in decoded.splitlines() if line.strip()]

    # 解析所有 vless:// 链接
    nodes = []
    errors = []

    for i, line in enumerate(lines, 1):
        if not line.startswith("vless://"):
            continue

        try:
            node = parse_vless_uri(line)
            nodes.append(node)
        except Exception as e:
            errors.append(f"链接 {i}: {e}")

    return nodes, errors


def to_clash_config(node: dict) -> dict:
    """将节点信息转换为 Clash Meta 代理配置。"""
    proxy = {
        "name": node["name"],
        "type": "vless",
        "server": node["server"],
        "port": node["port"],
        "uuid": node["uuid"],
        "udp": True,
    }

    # TLS 配置
    tls = node.get("tls", {})
    if tls.get("enabled"):
        proxy["tls"] = True
        if tls.get("sni"):
            proxy["servername"] = tls["sni"]
        if tls.get("fingerprint"):
            proxy["client-fingerprint"] = tls["fingerprint"]
        if tls.get("allow_insecure"):
            proxy["skip-cert-verify"] = True

        # Reality 配置
        if tls.get("reality"):
            reality_opts = {}
            if tls.get("public_key"):
                reality_opts["public-key"] = tls["public_key"]
            if tls.get("short_id"):
                reality_opts["short-id"] = tls["short_id"]
            if reality_opts:
                proxy["reality-opts"] = reality_opts
            if tls.get("flow"):
                proxy["flow"] = tls["flow"]

        # ALPN
        if tls.get("alpn"):
            proxy["alpn"] = tls["alpn"]

    # 传输层配置
    transport = node.get("transport", "tcp")
    if transport != "tcp":
        proxy["network"] = transport

    transport_config = node.get("transport_config", {})
    if transport == "ws":
        ws_opts = {}
        if transport_config.get("path"):
            ws_opts["path"] = transport_config["path"]
        if transport_config.get("host"):
            ws_opts["headers"] = {"Host": transport_config["host"]}
        if ws_opts:
            proxy["ws-opts"] = ws_opts
    elif transport == "grpc":
        if transport_config.get("service_name"):
            proxy["grpc-opts"] = {"grpc-service-name": transport_config["service_name"]}
    elif transport == "h2":
        h2_opts = {}
        if transport_config.get("path"):
            h2_opts["path"] = transport_config["path"]
        if transport_config.get("host"):
            h2_opts["host"] = transport_config["host"]
        if h2_opts:
            proxy["h2-opts"] = h2_opts

    return proxy


def print_node_summary(node: dict) -> None:
    """打印节点摘要信息。"""
    tls = node.get("tls", {})
    security = "reality" if tls.get("reality") else ("tls" if tls.get("enabled") else "none")

    print(f"  {node['name']}")
    print(f"    服务器: {node['server']}:{node['port']}")
    print(f"    传输: {node['transport']} | 安全: {security}")

    if tls.get("sni"):
        print(f"    SNI: {tls['sni']}")

    transport_config = node.get("transport_config", {})
    if node["transport"] == "ws" and transport_config.get("path"):
        print(f"    路径: {transport_config['path']}")

    print()


def main():
    """主函数，支持命令行参数。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="v2ray 订阅链接解析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 从 URL 获取订阅
  python v2ray_parser.py --url "https://example.com/sub"

  # 从 base64 内容解析
  python v2ray_parser.py --base64 "dmxlc3M6Ly8..."

  # 从文件读取
  python v2ray_parser.py --file subscription.txt

  # 输出为 JSON
  python v2ray_parser.py --url "https://..." --format json

  # 输出为 Clash 配置
  python v2ray_parser.py --url "https://..." --format clash

  # 保存到文件
  python v2ray_parser.py --url "https://..." --format json --output nodes.json
        """
    )

    # 输入源（三选一）
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--url", help="订阅链接 URL")
    input_group.add_argument("--base64", help="Base64 编码的订阅内容")
    input_group.add_argument("--file", help="包含订阅内容的文件路径")

    # 输出格式
    parser.add_argument(
        "--format", "-f",
        choices=["summary", "json", "clash"],
        default="summary",
        help="输出格式 (默认: summary)"
    )

    # 输出文件
    parser.add_argument("--output", "-o", help="输出文件路径")

    args = parser.parse_args()

    # 获取内容
    try:
        if args.url:
            print(f"正在获取订阅: {args.url}")
            content = fetch_url(args.url)
        elif args.base64:
            content = args.base64
        elif args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                content = f.read()
    except Exception as e:
        print(f"错误: 获取内容失败 - {e}", file=sys.stderr)
        sys.exit(1)

    # 解析订阅
    nodes, errors = parse_subscription(content)

    if errors:
        print(f"\n解析错误 ({len(errors)}):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    if not nodes:
        print("错误: 未找到有效的 VLESS 节点", file=sys.stderr)
        sys.exit(1)

    print(f"\n解析完成: 共 {len(nodes)} 个节点\n")

    # 输出结果
    if args.format == "summary":
        for i, node in enumerate(nodes, 1):
            print(f"[{i}]")
            print_node_summary(node)

    elif args.format == "json":
        output = json.dumps(nodes, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已保存到: {args.output}")
        else:
            print(output)

    elif args.format == "clash":
        clash_proxies = [to_clash_config(node) for node in nodes]
        try:
            import yaml
            output = yaml.dump(
                {"proxies": clash_proxies},
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )
        except ImportError:
            # 如果没有 pyyaml，输出 JSON 格式
            output = json.dumps({"proxies": clash_proxies}, ensure_ascii=False, indent=2)
            print("警告: 未安装 pyyaml，输出 JSON 格式", file=sys.stderr)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已保存到: {args.output}")
        else:
            print(output)


if __name__ == "__main__":
    main()
