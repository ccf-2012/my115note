#!/usr/bin/env python3
# encoding: utf-8

"""Batch rename 115网盘 files under a directory using regex replacements."""

from argparse import ArgumentParser, RawTextHelpFormatter
from pathlib import Path
from typing import Iterable
import re
import sys

from p115client import P115Client
from p115client.tool import iter_files_shortcut, iterdir
from p115client.tool.iterdir import overview_attr


def get_client(cookies: str | Path | None, cookies_path: str | None) -> P115Client:
    if cookies:
        return P115Client(cookies, check_for_relogin=True, app="chrome")
    if cookies_path:
        return P115Client(Path(cookies_path), check_for_relogin=True, app="chrome")
    default_path = Path("115-cookies.txt")
    if not default_path.exists():
        default_path = Path("./115-cookies.txt").expanduser()
    if default_path.exists():
        return P115Client(default_path)
    return P115Client(check_for_relogin=True)


def list_files(client: P115Client, cid: str | int, max_workers: int | None = None) -> Iterable[dict]:
    # use `iterdir` to list immediate children (non-recursive), including dirs
    return iterdir(
        client,
        cid=cid,
        max_workers=max_workers,
        app="chrome",
    )


def build_rename_tasks(files: Iterable[dict], pattern: re.Pattern, replacement: str, suffixes: list[str] | None) -> list[tuple[int | str, str]]:
    """Build rename tasks for immediate children (files and directories).

    Directories are always considered; `suffixes` only filters files.
    """
    tasks: list[tuple[int | str, str]] = []
    for file_info in files:
        try:
            attr = overview_attr(file_info)
        except Exception:
            # fallback: try to read name/id directly
            name = file_info.get("name")
            fid = file_info.get("id") or file_info.get("fid") or file_info.get("file_id")
            is_dir = file_info.get("is_dir") if "is_dir" in file_info else None
        else:
            name = attr.name
            fid = attr.id
            is_dir = attr.is_dir

        # print(f"Checking entry: {name}")
        if not name:
            continue
        if not is_dir and suffixes:
            ext = Path(name).suffix.lower().lstrip(".")
            if ext not in suffixes:
                continue
        if not pattern.search(name):
            continue
        new_name = pattern.sub(replacement, name)
        # print(f"Matched: {name} -> {new_name}")
        if not new_name or new_name == name:
            continue
        tasks.append((fid, new_name))
    return tasks


def perform_rename(client: P115Client, tasks: list[tuple[int | str, str]], app: str = "os_windows") -> dict:
    if not tasks:
        return {"success": True, "renamed": 0}
    payload = {str(fid): new_name for fid, new_name in tasks}
    try:
        resp = client.fs_rename_app(payload, app=app)
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "renamed": len(tasks), "response": resp}


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main() -> int:
    parser = ArgumentParser(
        description="使用正则批量重命名 115 网盘目录下的文件",
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument("cid", help="目录 id 或 pickcode")
    parser.add_argument("-p", "--pattern", required=True, help="正则匹配模式")
    parser.add_argument("-r", "--replace", default="", help="替换内容（默认删除匹配部分）")
    parser.add_argument("-s", "--suffix", help="只改名指定后缀，多个用逗号分隔，例如 mkv,mp4")
    parser.add_argument("-c", "--cookies", help="115 登录 cookies 字符串")
    parser.add_argument("-cp", "--cookies-path",  default="./115-cookies.txt", help="cookies 文件路径")
    parser.add_argument("-m", "--max-workers", type=int, help="iter_files_shortcut 最大工作线程数")
    parser.add_argument("--app", default="os_windows", help="重命名 API 使用的 app，默认 os_windows")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要改名的文件，不执行重命名")
    parser.add_argument("-y", "--yes", action="store_true", help="直接执行，不提示确认")
    args = parser.parse_args()

    try:
        regex = re.compile(args.pattern)
    except re.error as exc:
        print(f"无效正则表达式: {exc}")
        return 2

    suffixes = None
    if args.suffix:
        suffixes = [part.strip().lower() for part in args.suffix.split(",") if part.strip()]

    if cookies := args.cookies:
        client = P115Client(cookies, app="chrome")
    elif cookies_path := args.cookies_path:
        client = P115Client(Path(cookies_path), app="chrome")
    else:
        cookies_path = Path("./115-cookies.txt")
        if not cookies_path.exists():
            cookies_path = Path("./115-cookies.txt").expanduser()
        if cookies_path.exists():
            client = P115Client(cookies_path, app='chrome')

    print(f"登录应用: {client.login_app()}")
    print(f"扫描目录: {args.cid}")

    files = list_files(client, args.cid, args.max_workers)
    tasks = build_rename_tasks(files, regex, args.replace, suffixes)

    if not tasks:
        print("没有匹配的文件需要重命名。")
        return 0

    print(f"找到 {len(tasks)} 个改名任务：")
    for fid, new_name in tasks:
        print(f"  {fid} -> {new_name}")

    if args.dry_run:
        print("dry run 模式，未执行重命名。")
        return 0

    if not args.yes:
        if not confirm("确认执行改名吗？[y/N] "):
            print("已取消。")
            return 0

    result = perform_rename(client, tasks, app=args.app)
    if result.get("success"):
        print(f"已提交 {result['renamed']} 个改名请求。")
        return 0
    print("改名失败。", result)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
