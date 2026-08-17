"""
向 user_info.csv 添加用户的命令行脚本。

# 全部随机生成（uid、pwd、session、last_time）
/opt/miniconda3/envs/py311/bin/python add_user.py

# 指定 uid，pwd 随机
/opt/miniconda3/envs/py311/bin/python add_user.py --uid 123456

# 指定 pwd，uid 随机
/opt/miniconda3/envs/py311/bin/python add_user.py --pwd MyPass8x

# 全部指定
/opt/miniconda3/envs/py311/bin/python add_user.py --uid 123456 --pwd MyPass8x

"""

from __future__ import annotations

import argparse
import sys

from src.user_auth import add_user


def main() -> None:
    """
    解析命令行参数并添加用户。

    参数:
        无（通过 argparse 读取 --uid、--pwd）

    返回:
        None
    """
    parser = argparse.ArgumentParser(
        description="向 data/user_info.csv 添加用户；uid、pwd 可选，未提供则随机生成。"
    )
    parser.add_argument(
        "--uid",
        type=str,
        default=None,
        help="用户 ID（6 位数字），不传则随机生成",
    )
    parser.add_argument(
        "--pwd",
        type=str,
        default=None,
        help="8 位数字+字母密码，不传则随机生成",
    )
    args = parser.parse_args()

    try:
        user = add_user(uid=args.uid, pwd=args.pwd)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    print("用户已添加:")
    print(f"  uid:      {user.uid}")
    print(f"  pwd:      {user.pwd}")
    print(f"  session:  {user.session}")
    print(f"  nickname: {user.nickname}")
    print(f"  is_show:  {user.is_show}")
    print(f"  last_time:{user.last_time}")


if __name__ == "__main__":
    main()
