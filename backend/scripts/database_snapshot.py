"""Run with PYTHONPATH=backend; explicit paths only, no active database overwrite."""
import argparse
import sqlite3
from pathlib import Path

from app.storage.backup import snapshot_database


def main():
    parser = argparse.ArgumentParser(description="梦卡数据库备份 / 恢复到新路径（不会覆盖现有文件）")
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        snapshot_database(args.source, args.destination, restore=args.action == "restore")
    except (OSError, ValueError, sqlite3.Error):
        print("操作未完成：请检查源文件完整性、目标是否已存在及目录权限；未覆盖现有数据库")
        return 1
    print("备份完成" if args.action == "backup" else "已恢复到新路径，历史与额度保留，用户需重新登录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
