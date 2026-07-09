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
        for _ in uploader.iter_upload(reporthook=t.update):
            pass

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
    for path, relative_path in iter_upload_paths(args.path):
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
            results.append({"path": str(path), "status": "ok", "result": result})

    failures = [item for item in results if item["status"] != "ok"]
    if failures:
        print(f"\nFinished with {len(failures)} failed uploads.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

