#!/usr/bin/env python3
"""
本地测试脚本：加载 test.env 并运行 merge_clash.py
用法: python run_test.py
"""

import os
import subprocess
import sys
from pathlib import Path

def load_env(path: str) -> dict:
    """从 .env 文件加载环境变量（支持 # 注释）。"""
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env

def main():
    env_path = Path(__file__).parent / "test.env"
    if not env_path.exists():
        print(f"错误: {env_path} 不存在")
        sys.exit(1)

    env_vars = load_env(str(env_path))

    print("=" * 50)
    print("Clash 配置合并 - 测试运行")
    print("=" * 50)
    print()
    print("环境变量:")
    for k, v in env_vars.items():
        display = v if len(v) < 60 else v[:57] + "..."
        print(f"  {k}={display}")
    print()

    # 合并当前环境和 test.env 中的变量
    run_env = os.environ.copy()
    run_env.update(env_vars)

    # 运行合并脚本
    script = Path(__file__).parent / "merge_clash.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        env=run_env,
        cwd=str(Path(__file__).parent),
    )

    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
