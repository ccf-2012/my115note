import argparse
from pathlib import Path
from p115client import P115Client
from p115client.tool import P115MultipartUpload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a file or URL to 115 with a target pid.")
    parser.add_argument(
        "path",
        help="Local file path or URL to upload.",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = P115Client(Path(args.cookies).expanduser())

    uploader = P115MultipartUpload.from_path(
        args.path,
        user_id=client.user_id,
        user_key=client.user_key,
        pid=args.pid,
    )

    # NOTE: 返回字典说明秒传成功
    if isinstance(uploader, dict):
        print(uploader)
        return

    from os.path import getsize
    from tqdm import tqdm

    # NOTE: 文件总大小需要你自己获取，`reporthook`只做增量推送
    with tqdm(total=getsize(args.path), unit="B", unit_scale=True, desc="Uploading") as t:
        # NOTE: `iter_upload` 支持其它请求模块，例如 urllib3
        #     from urllib3_request import request
        #     uploader.iter_upload(request=request)
        for _ in uploader.iter_upload(reporthook=t.update):
            pass
    print(uploader.complete())


if __name__ == "__main__":
    main()

