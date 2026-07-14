#!/usr/bin/env python3
# encoding: utf-8

"""Reorganize 115网盘 files based on local .strm files."""

from argparse import ArgumentParser, RawTextHelpFormatter
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import posixpath
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any

from p115client import P115Client, P115OpenClient

def get_client(cookies: str | Path | None, cookies_path: str | None) -> P115OpenClient:
    if cookies:
        client = P115Client(cookies, check_for_relogin=True, app="chrome")
    elif cookies_path:
        client = P115Client(Path(cookies_path), check_for_relogin=True, app="chrome")
    else:
        default_path = Path("115-cookies.txt")
        if not default_path.exists():
            default_path = Path("./115-cookies.txt").expanduser()
        if default_path.exists():
            client = P115Client(default_path)
        else:
            client = P115Client(check_for_relogin=True)
    return client.login_another_open()

def fs_makedirs_open(client: P115OpenClient, path: str, pid: int | str = 0) -> dict:
    parts = [p for p in path.split("/") if p]
    current_pid = pid
    
    for part in parts:
        found = False
        from p115client.tool import iterdir
        try:
            for item in iterdir(client, cid=current_pid):
                if item.get("is_dir") and item.get("name") == part:
                    current_pid = int(item["id"])
                    found = True
                    break
        except Exception:
            pass
            
        if not found:
            res = client.fs_mkdir(part, pid=current_pid)
            if isinstance(res, dict) and res.get("state") is True:
                current_pid = int(res["data"]["file_id"])
            elif isinstance(res, dict) and res.get("code") == 20004:
                # Directory already exists, find its ID
                found_after = False
                for item in iterdir(client, cid=current_pid):
                    if item.get("is_dir") and item.get("name") == part:
                        current_pid = int(item["id"])
                        found_after = True
                        break
                if not found_after:
                    return {"state": False, "error": f"Folder already exists but could not retrieve its ID: {part}"}
            else:
                err_msg = res.get("error") or res.get("message") if isinstance(res, dict) else str(res)
                return {"state": False, "error": f"Failed to create folder '{part}' under '{current_pid}': {err_msg}"}
                
    return {"state": True, "error": "", "data": {"file_id": str(current_pid)}}

def parse_strm_file(file_path: Path, client: P115OpenClient) -> Optional[dict]:
    try:
        content = file_path.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"Error reading local file {file_path}: {e}")
        return None

    if not content:
        return None

    # Get first line starting with http:// or https://
    url = None
    for line in content.splitlines():
        line_str = line.strip()
        if line_str.startswith(("http://", "https://")):
            url = line_str
            break

    if not url:
        return None

    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        raw_id = params.get("id", [None])[0]
        pickcode = params.get("pickcode", [None])[0]
        
        fid = None
        if raw_id:
            fid = client.to_id(raw_id)
        elif pickcode:
            fid = client.to_id(pickcode)
            
        if not fid:
            print(f"Warning: No valid ID or pickcode found in {file_path.name}")
            return None
            
        # Parse path and extract old_115_path & url_prefix_path
        decoded_path = urllib.parse.unquote(parsed.path)
        if "//" in decoded_path:
            prefix, _, suffix = decoded_path.partition("//")
            old_115_path = "/" + suffix.lstrip("/")
            url_prefix_path = prefix + "//"
        else:
            url_prefix_path = "/"
            old_115_path = decoded_path
            for mount_p in ["/d/open115", "/d/115", "/d/open", "/d"]:
                if decoded_path.startswith(mount_p):
                    url_prefix_path = mount_p + "/"
                    old_115_path = "/" + decoded_path[len(mount_p):].lstrip("/")
                    break
                    
        file_name = posixpath.basename(old_115_path)
        
        return {
            "strm_path": file_path,
            "url": url,
            "fid": fid,
            "pickcode": pickcode,
            "parsed_url": parsed,
            "old_115_path": old_115_path,
            "url_prefix_path": url_prefix_path,
            "file_name": file_name
        }
    except Exception as e:
        print(f"Error parsing URL from {file_path}: {e}")
        return None

def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False

def main() -> int:
    parser = ArgumentParser(
        description="根据本地 .strm 文件，反向整理 115 网盘上的文件目录结构",
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument("strm_dir", help="本地待扫描的 .strm 目录路径")
    parser.add_argument("-sr", "--src-root", help="计算相对路径的本地源根目录，默认与 strm_dir 相同")
    parser.add_argument("-t", "--target-root", default="/emby2", help="115网盘上的目标根目录，默认: /emby2")
    parser.add_argument("-c", "--cookies", help="115 登录 cookies 字符串")
    parser.add_argument("-cp", "--cookies-path", help="cookies 文件路径 (默认自动查找 115-cookies.txt)")
    parser.add_argument("--update-local", action="store_true", help="移动 115 文件后，同步更新本地 .strm 文件中的 URL 路径")
    parser.add_argument("--dry-run", action="store_true", help="测试模式：只打印将要执行的操作，不实际修改网盘或本地文件")
    parser.add_argument("-y", "--yes", action="store_true", help="直接执行，不提示确认")
    args = parser.parse_args()

    strm_dir_path = Path(args.strm_dir).resolve()
    if not strm_dir_path.exists() or not strm_dir_path.is_dir():
        print(f"错误: 本地 strm_dir 目录不存在或不是目录: {args.strm_dir}")
        return 1

    src_root_path = Path(args.src_root or args.strm_dir).resolve()
    target_root = args.target_root.rstrip("/")
    if not target_root.startswith("/"):
        target_root = "/" + target_root

    print(f"正在扫描本地 .strm 文件: {strm_dir_path}")
    print(f"源根目录 (计算相对路径): {src_root_path}")
    print(f"115 目标根目录: {target_root}")

    strm_files = list(strm_dir_path.rglob("*.strm"))
    if not strm_files:
        print("未找到任何 .strm 文件。")
        return 0

    print(f"找到 {len(strm_files)} 个本地 .strm 文件，正在解析 URL...")

    # Re-use client cookies logic
    client = get_client(args.cookies, args.cookies_path)
    print(f"成功登录 115 账号")

    tasks = []
    for f in strm_files:
        info = parse_strm_file(f, client)
        if info:
            tasks.append(info)

    if not tasks:
        print("没有成功解析出任何 115 文件的 URL。")
        return 0

    # Calculate mapping and group by target directories
    # We will build a list of movements: (fid, old_115_path, new_115_dir_path, new_115_path, local_strm_info)
    move_tasks = []
    skipped_count = 0

    for task in tasks:
        fid = task["fid"]
        file_name = task["file_name"]
        old_115_path = task["old_115_path"]

        # Calculate relative directory path of local .strm file parent directory relative to src_root
        local_strm_file = task["strm_path"]
        try:
            rel_dir = local_strm_file.parent.relative_to(src_root_path)
        except ValueError:
            print(f"警告: 本地文件 {local_strm_file} 不在源根目录 {src_root_path} 下，将使用其直接父目录名")
            rel_dir = Path(local_strm_file.parent.name)

        # Compute new 115 target directory path
        new_115_dir_path = posixpath.join(target_root, rel_dir.as_posix())
        new_115_path = posixpath.join(new_115_dir_path, file_name)

        # Check if the file path is already exactly matching the target path
        if old_115_path == new_115_path:
            skipped_count += 1
            continue

        move_tasks.append({
            "fid": fid,
            "file_name": file_name,
            "old_115_path": old_115_path,
            "new_115_dir_path": new_115_dir_path,
            "new_115_path": new_115_path,
            "task": task
        })

    print(f"分析完成：共需移动 {len(move_tasks)} 个文件 (已在本地 URL 目标位置跳过 {skipped_count} 个)。")

    if not move_tasks:
        print("所有文件均已在目标位置，无需移动。")
        return 0

    # Print summary of proposed moves
    print("\n计划执行以下整理操作：")
    for task in move_tasks:
        print(f"  [移动] 115文件 ID: {task['fid']}")
        print(f"    源: {task['old_115_path']}")
        print(f"    目标: {task['new_115_path']}")
        if args.update_local:
            print(f"    [更新本地] {task['task']['strm_path'].name}")

    if args.dry_run:
        print("\n[测试模式] 未对网盘或本地文件执行任何实际修改。")
        return 0

    if not args.yes:
        if not confirm("\n确认执行上述整理操作吗？[y/N] "):
            print("操作已取消。")
            return 0

    # Step 5: Create target directories on 115 sequentially to obtain folder IDs
    print("\n正在 115 网盘上创建目标目录结构...")
    unique_target_dirs = sorted(list(set(task["new_115_dir_path"] for task in move_tasks)))
    dir_path_to_id = {}

    for dpath in unique_target_dirs:
        try:
            # fs_makedirs_open returns leaf folder ID in data['file_id']
            res = fs_makedirs_open(client, dpath)
            if isinstance(res, dict) and res.get("state") is True:
                folder_id = int(res["data"]["file_id"])
                dir_path_to_id[dpath] = folder_id
                print(f"  [创建/确认目录] {dpath} -> ID: {folder_id}")
            else:
                err_msg = res.get("error") if isinstance(res, dict) else str(res)
                print(f"错误: 无法在 115 上创建目录 {dpath}: {err_msg}")
                return 1
        except Exception as e:
            print(f"错误: 创建目录 {dpath} 时发生异常: {e}")
            return 1

    # Step 6: Group file moves by target directory ID, check if already present, and execute
    moves_by_pid = {}
    for task in move_tasks:
        dpath = task["new_115_dir_path"]
        pid = dir_path_to_id.get(dpath)
        if pid is not None:
            moves_by_pid.setdefault(pid, []).append(task)

    print("\n正在执行文件移动操作...")
    success_count = 0
    failure_count = 0
    updated_local_count = 0

    for pid, tasks_chunk in moves_by_pid.items():
        target_path = tasks_chunk[0]["new_115_dir_path"]
        
        # Check existing items in this target folder on 115 to skip files that have already been moved
        existing_ids = set()
        from p115client.tool import iterdir
        try:
            for item in iterdir(client, cid=pid):
                if not item.get("is_dir"):
                    existing_ids.add(int(item["id"]))
        except Exception as e:
            print(f"  [警告] 无法读取目标目录 {target_path} (ID: {pid}) 中的文件列表: {e}")

        # Filter out tasks that are already in the target folder
        to_move_tasks = []
        for task in tasks_chunk:
            fid = task["fid"]
            if fid in existing_ids:
                print(f"  [跳过] 115文件 ID {fid} ({task['file_name']}) 已经在目标目录 {target_path}")
                # Auto-heal the local strm if update_local is requested and URL is outdated
                if args.update_local:
                    local_path = task["task"]["strm_path"]
                    old_url = task["task"]["url"]
                    parsed_url = task["task"]["parsed_url"]
                    
                    url_prefix_path = task["task"]["url_prefix_path"]
                    new_path_seg = task["new_115_path"]
                    
                    new_decoded_url_path = url_prefix_path + new_path_seg
                    new_url_path_quoted = urllib.parse.quote(new_decoded_url_path, safe="/")
                    new_url = parsed_url._replace(path=new_url_path_quoted).geturl()
                    
                    if old_url != new_url:
                        try:
                            local_path.write_text(new_url, encoding="utf-8")
                            updated_local_count += 1
                            print(f"    [修复本地] {local_path.name}")
                        except Exception as le:
                            print(f"    [警告] 更新本地 strm 失败 {local_path.name}: {le}")
                success_count += 1
            else:
                to_move_tasks.append(task)

        if not to_move_tasks:
            continue

        fids_to_move = [t["fid"] for t in to_move_tasks]
        print(f"  正在将 {len(fids_to_move)} 个文件移动到 {target_path} (ID: {pid})...")
        
        try:
            res = client.fs_move(fids_to_move, pid=pid)
            if isinstance(res, dict) and res.get("state") is True:
                print(f"    成功移动 {len(fids_to_move)} 个文件。")
                success_count += len(to_move_tasks)
                
                # Update local strm files
                if args.update_local:
                    for task in to_move_tasks:
                        local_path = task["task"]["strm_path"]
                        old_url = task["task"]["url"]
                        parsed_url = task["task"]["parsed_url"]
                        
                        url_prefix_path = task["task"]["url_prefix_path"]
                        new_path_seg = task["new_115_path"]
                        
                        new_decoded_url_path = url_prefix_path + new_path_seg
                        new_url_path_quoted = urllib.parse.quote(new_decoded_url_path, safe="/")
                        new_url = parsed_url._replace(path=new_url_path_quoted).geturl()
                        
                        try:
                            local_path.write_text(new_url, encoding="utf-8")
                            updated_local_count += 1
                        except Exception as le:
                            print(f"      [警告] 更新本地 strm 文件失败 {local_path.name}: {le}")
            else:
                err_msg = res.get("error") or res.get("message") if isinstance(res, dict) else str(res)
                print(f"    [失败] 批量移动文件失败: {err_msg}")
                failure_count += len(to_move_tasks)
        except Exception as e:
            print(f"    [异常] 移动文件时发生错误: {e}")
            failure_count += len(to_move_tasks)

        # Brief delay to prevent hitting 115 rate limits
        time.sleep(0.5)

    print(f"\n整理任务完成统计：")
    print(f"  成功移动/校验: {success_count} 个文件")
    print(f"  移动失败: {failure_count} 个文件")
    if args.update_local:
        print(f"  更新本地 strm 文件: {updated_local_count} 个")

    return 0 if failure_count == 0 else 2

if __name__ == "__main__":
    import sys
    sys.exit(main())
