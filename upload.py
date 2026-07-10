import argparse
from pathlib import Path
from urllib.parse import urlparse

from p115client import P115Client
from p115client.tool import P115MultipartUpload
from p115client.tool.edit import makedir
import p115client.tool.upload as p115client_tool_upload
import p115oss.api as p115oss_api
import p115oss.upload as p115oss_upload
from p115oss.oss import oss_url
from tqdm import tqdm
import traceback


def patch_oss_multipart_upload_part_iter() -> None:
    orig = p115client_tool_upload.oss_multipart_upload_part_iter

    def wrapper(*args, **kwargs):
        if "url" in kwargs:
            url = kwargs.pop("url")
            return orig(url, *args, **kwargs)
        if args:
            return orig(*args, **kwargs)
        raise TypeError("oss_multipart_upload_part_iter() missing 1 required positional argument: 'url_or_key'")

    p115client_tool_upload.oss_multipart_upload_part_iter = wrapper


def is_url(path: str) -> bool:
    scheme = urlparse(path).scheme.lower()
    return scheme in ("http", "https")


def patch_appversion(appversion: str = "36.2.28") -> None:
    orig_api_upload_init = p115oss_api.upload_init
    orig_upload_file_init = p115oss_upload.upload_file_init

    def upload_init(payload: dict, *, async_: bool = False, **request_kwargs):
        if isinstance(payload, dict) and "appversion" not in payload:
            payload = {"appversion": appversion, **payload}
        return orig_api_upload_init(payload, async_=async_, **request_kwargs)

    def patch_response(resp: dict, endpoint: str | None = None) -> dict:
        data = resp.get("data")
        if isinstance(data, dict) and "url" not in data:
            bucket = data.get("bucket")
            obj = data.get("object")
            if bucket and obj:
                data["url"] = oss_url(
                    obj,
                    bucket=bucket,
                    endpoint=endpoint or "https://oss-cn-shenzhen.aliyuncs.com",
                )
        return resp

    def upload_file_init(
        file,
        pid=0,
        filename="",
        filesha1="",
        filesize=-1,
        user_id="",
        user_key="",
        *,
        async_: bool = False,
        **request_kwargs,
    ):
        result = orig_upload_file_init(
            file,
            pid=pid,
            filename=filename,
            filesha1=filesha1,
            filesize=filesize,
            user_id=user_id,
            user_key=user_key,
            async_=async_,
            **request_kwargs,
        )
        if async_:
            async def wrapper():
                resp = await result
                return patch_response(resp, request_kwargs.get("endpoint"))

            return wrapper()
        return patch_response(result, request_kwargs.get("endpoint"))

    p115oss_api.upload_init = upload_init
    p115oss_upload.upload_init = upload_init
    p115oss_upload.upload_file_init = upload_file_init
    p115client_tool_upload.upload_file_init = upload_file_init


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a file or a directory recursively to 115 with a target pid."
    )
    parser.add_argument(
        "path",
        help="Local file path, local directory path, or URL to upload.",
    )
    parser.add_argument(
        "--pid",
        type=int,
        default=0,
        help="Target parent directory id on 115 (default: 0).",
    )
    parser.add_argument(
        "--cookies",
        default="./115-cookies.txt",
        help="Path to 115 cookies file (default: ./115-cookies.txt).",
    )
    parser.add_argument(
        "--appversion",
        default="36.2.28",
        help="App version header used for upload initialization.",
    )
    parser.add_argument(
        "--exts",
        default="mkv,mp4,ts,iso,avi,rmvb,wmv,webm,mp3,flac,ape,wav,acc,ogg,ass,m4a,srt,vtt,sub",
        help=(
            "Comma-separated list of allowed file extensions (no dots). "
            "Defaults to common media/subtitle/audio types. Example: mkv,mp4,avi"
        ),
    )
    return parser.parse_args()


def iter_upload_paths(path: str):
    if is_url(path):
        yield path, Path(urlparse(path).path).name or path
        return

    src = Path(path).expanduser()
    if src.is_dir():
        for file_path in sorted(src.rglob("*")):
            if file_path.is_file():
                relative_name = file_path.relative_to(src).as_posix()
                yield file_path, relative_name
    else:
        if not src.exists():
            raise FileNotFoundError(f"File or directory not found: {src}")
        yield src, src.name


def upload_path(path, filename, client, pid: int):
    uploader = P115MultipartUpload.from_path(
        path,
        pid=pid,
        filename=filename,
        user_id=client.user_id,
        user_key=client.user_key,
    )

    if isinstance(uploader, dict):
        return uploader

    total = None
    if isinstance(path, Path) and path.exists():
        try:
            total = path.stat().st_size
        except OSError:
            total = None

    with tqdm(total=total, unit="B", unit_scale=True, desc=f"Uploading {filename}") as t:
        # Print uploader debug info before actual upload to help diagnose auth errors
        try:
            if hasattr(uploader, "url"):
                print(f"uploader.url: {uploader.url}")
            if hasattr(uploader, "upload_id"):
                print(f"uploader.upload_id: {uploader.upload_id}")
            # Try to get a signed upload url for part 1 (may raise if not available)
            try:
                upload_url_info = uploader.upload_url(1)
                print(f"uploader.upload_url(1): {upload_url_info}")
            except Exception:
                # not critical, keep going
                pass

            for _ in uploader.iter_upload(reporthook=t.update):
                pass
        except Exception:
            # Print full traceback to help pinpoint where 401 originates
            print("Upload raised exception:")
            traceback.print_exc()
            raise

    return uploader.complete()


def ensure_remote_dirs(client: P115Client, target_pid: int, relative_dir: str) -> int:
    if not relative_dir:
        return target_pid
    return makedir(client, relative_dir, pid=target_pid, contain_dir=True)


def main() -> None:
    args = parse_args()
    patch_oss_multipart_upload_part_iter()
    patch_appversion(args.appversion)
    client = P115Client(Path(args.cookies).expanduser())

    results = []
    dir_cache: dict[str, int] = {}
    # Build allowed extensions set from CLI (normalize to lowercase, no leading dots)
    exts_raw = args.exts or ""
    allowed_exts = set()
    for e in (x.strip().lower() for x in exts_raw.split(",")):
        if not e:
            continue
        if e.startswith("."):
            e = e[1:]
        allowed_exts.add(e)
    for path, relative_path in iter_upload_paths(args.path):
        # Filter by extension if configured
        try:
            rel_name = relative_path if isinstance(relative_path, str) else str(relative_path)
        except Exception:
            rel_name = str(relative_path)
        suffix = ""
        if "." in rel_name:
            suffix = rel_name.rsplit(".", 1)[1].lower()
        if allowed_exts and suffix not in allowed_exts:
            print(f"Skipping (ext filter): {rel_name} -> .{suffix}")
            results.append({"path": str(path), "status": "skip", "reason": "ext_filter", "ext": suffix})
            continue
        relative_dir = Path(relative_path).parent
        if relative_dir == Path("."):
            target_pid = args.pid
        else:
            dir_key = relative_dir.as_posix()
            target_pid = dir_cache.get(dir_key)
            if target_pid is None:
                target_pid = ensure_remote_dirs(client, args.pid, dir_key)
                dir_cache[dir_key] = target_pid

        print(f"\nUploading: {path} -> {relative_path} (pid={target_pid})")
        try:
            result = upload_path(path, Path(relative_path).name, client, target_pid)
        except Exception as exc:
            print(f"Upload failed: {path}\n  {exc}")
            results.append({"path": str(path), "status": "fail", "error": str(exc)})
        else:
            print(result)
            # Detect fast-upload (秒传) from the response.
            # The API typically signals reuse/秒传 with either `reuse: True`
            # or `status` values like 2 or 7 (existence / reused on server).
            is_fast = False
            status_val = None
            if isinstance(result, dict):
                is_fast = bool(result.get("reuse"))
                status_val = result.get("status")
            if is_fast or status_val in (2, 7):
                info = []
                if isinstance(result, dict):
                    pick = result.get("data", {}).get("pickcode") or result.get("pickcode")
                    fid = result.get("data", {}).get("id") or result.get("fileid")
                    if pick:
                        info.append(f"pickcode={pick}")
                    if fid:
                        info.append(f"id={fid}")
                print("秒传成功。" + (" (" + ", ".join(info) + ")" if info else ""))
            else:
                print("已完整上传（非秒传）。")

            results.append({"path": str(path), "status": "ok", "result": result})

    failures = [item for item in results if item["status"] != "ok"]
    # Summary counts
    total_files = len(results)
    skipped = [r for r in results if r.get("status") == "skip"]
    failed = [r for r in results if r.get("status") == "fail"]
    ok_items = [r for r in results if r.get("status") == "ok"]
    # Count fast-upload (秒传) among ok items
    fast_count = 0
    for r in ok_items:
        res = r.get("result")
        if isinstance(res, dict):
            if bool(res.get("reuse")) or res.get("status") in (2, 7):
                fast_count += 1
    uploaded_count = len(ok_items) - fast_count

    print("\nSummary:")
    print(f"  Total files processed: {total_files}")
    print(f"  Skipped by ext filter: {len(skipped)}")
    print(f"  Successful fast-upload (秒传): {fast_count}")
    print(f"  Uploaded (actual upload performed): {uploaded_count}")
    print(f"  Failed uploads: {len(failed)}")

    if failed:
        print(f"\nFinished with {len(failed)} failed uploads.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

