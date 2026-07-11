#!/usr/bin/env python3
# encoding: utf-8

"""Batch rename 115网盘 files under a directory using regex replacements."""

from argparse import ArgumentParser, RawTextHelpFormatter
from pathlib import Path
from typing import Iterable
import re

from p115client import P115Client
from p115client.tool import iterdir
from p115client.tool.iterdir import overview_attr
import time


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


def perform_rename(client: P115Client, tasks: list[tuple[int | str, str]]) -> dict:
    """Use webapi `fs_rename` first; if it fails, fall back to per-item `fs_rename` calls."""
    if not tasks:
        return {"success": True, "renamed": 0}

    try:
        resp = client.fs_rename(tasks)
    except Exception as e:
        resp = {"state": False, "error": str(e)}

    if isinstance(resp, dict) and resp.get("state"):
        return {"success": True, "renamed": len(tasks), "response": resp, "note": "used fs_rename (webapi)"}

    per_results = []
    count_ok = 0
    for fid, new_name in tasks:
        try:
            r = client.fs_rename((fid, new_name))
            ok = isinstance(r, dict) and (r.get("state") is True or r.get("errno") == 0)
            per_results.append({"fid": fid, "ok": ok, "response": r})
            if ok:
                count_ok += 1
        except Exception as e:
            per_results.append({"fid": fid, "ok": False, "error": str(e)})
        time.sleep(0.12)

    return {
        "success": count_ok == len(tasks),
        "renamed_attempted": len(tasks),
        "renamed": count_ok,
        "response": resp,
        "fallback": per_results,
    }


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
    parser.add_argument("--batch-size", type=int, default=200, help="每次提交改名请求的批量大小，默认 200")
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

    client = get_client(args.cookies, args.cookies_path)
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

    batch_size = getattr(args, "batch_size", 200)
    total_submitted = 0
    for i in range(0, len(tasks), batch_size):
        chunk = tasks[i : i + batch_size]
        result = perform_rename(client, chunk)
        submitted = result.get("renamed", result.get("renamed_attempted", len(chunk)))
        total_submitted += submitted
        if result.get("fallback"):
            print(
                f"批次{i // batch_size + 1}: 回退逐条重命名，成功 {result['renamed']}/{len(chunk)}"
            )
        elif result.get("note"):
            print(f"批次{i // batch_size + 1}: 批量重命名成功，共 {submitted} 个")
        else:
            print(f"批次{i // batch_size + 1}: 批量重命名失败，成功 {submitted}/{len(chunk)} 个")
    print(f"共处理 {len(tasks)} 个改名任务，已提交 {total_submitted} 次重命名请求")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
