#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__version__ = (0, 0, 1)
__all__ = ["make_strm_func"]

if __name__ == "__main__":
    from argparse import ArgumentParser, RawTextHelpFormatter

    parser = ArgumentParser(
        description="快速创建 115 STRM", 
        formatter_class=RawTextHelpFormatter, 
    )
    parser.add_argument("cid", nargs="?", help="待拉取的目录 id 或 pickcode")
    parser.add_argument("-c", "--cookies", help="115 登录 cookies，优先级高于 -cp/--cookies-path")
    parser.add_argument("-cp", "--cookies-path", help="cookies 文件保存路径，默认为当前工作目录下的 115-cookies.txt")
    parser.add_argument("-s", "--save-dir", default="", help="保存在本地的目录，默认为当前工作目录")
    parser.add_argument("-b", "--base-url", default="", help="302 服务器的基地址，如果为空（默认），则在 STRM 文件中直接保存路径")
    parser.add_argument("-bp", "--base-path", default="", help="302 服务器的基路径，如果为空（默认），则在 STRM 文件中直接保存路径")
    parser.add_argument("-f", "--filter", help="""筛选条件：
  - 默认不进行筛选
  - 数字 1-7 其一，筛选特定类型文件
    - 1: 文档
    - 2: 图片
    - 3: 音频
    - 4: 视频
    - 5: 压缩包
    - 6: 应用
    - 7: 书籍
  - 后缀（扩展名），如果有多个用英文逗号,隔开""")
    parser.add_argument("-m", "--max-workers", type=int, help="最大工作线程数，默认自动确定")
    args = parser.parse_args()
    if not args.cid:
        parser.parse_args(["-h"])
        raise SystemExit(0)

from collections.abc import Callable
from os import PathLike
from typing import Literal

from p115client import P115Client
from p115client.tool import make_strm

def make_strm_func(
    client: str | PathLike | P115Client, 
    cid: int | str = 0, 
    save_dir: str = "", 
    predicate: None | Literal[1, 2, 3, 4, 5, 6, 7] | str | tuple[str, ...] | Callable[[dict], bool] = None, 
    base_url: str = "", 
    base_path: str = "",
    max_workers: None | int = None, 
) -> dict:
    """快速创建 STRM 文件

    :param client: 115 客户端或 cookies
    :param cid: 目录 id 或 pickcode
    :param save_dir: 保存在本地的目录，默认为当前工作目录
    :param predicate: 断言

        - 如果为 None，则不进行筛选
        - 如果为整数，则筛选某一类型的文件

            - 1: 文档
            - 2: 图片
            - 3: 音频
            - 4: 视频
            - 5: 压缩包
            - 6: 应用
            - 7: 书籍

        - 如果是 str 或元组，则是后缀或一组后缀，筛选这些后缀的文件
        - 如果是 Callable，则逐个对获取到的文件信息调用它，返回值为 True 才保留

    :param base_url: 302 服务器的基地址，如果为空，则在 STRM 文件中直接保存路径
    :param max_workers: 最大并发数，如果为 None，则自动确定
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)

    try:
        result = make_strm(client, 
                cid=cid, 
                save_dir=save_dir, 
                predicate=predicate, 
                base_url=base_url,
                app='harmony',
                clean=True,
                replace=False,
                olist_url=True,
                base_path=base_path,
                max_workers=max_workers)
        return result
    except Exception as e:
        print('生成strm出错: %s' % e)
        raise e


if __name__ == "__main__":
    from pathlib import Path

    if cookies := args.cookies:
        client = P115Client(cookies, check_for_relogin=True)
    elif cookies_path := args.cookies_path:
        client = P115Client(Path(cookies_path), check_for_relogin=True)
    else:
        cookies_path = Path("115-cookies.txt")
        if not cookies_path.exists():
            cookies_path = Path("~/115-cookies.txt").expanduser()
        if cookies_path.exists():
            client = P115Client(cookies_path)
        else:
            client = P115Client(check_for_relogin=True)
    if predicate := args.filter:
        if predicate in ("1", "2", "3", "4", "5", "6", "7"):
            predicate = int(predicate)
        elif "," in predicate:
            predicate = tuple(predicate.split(","))

    result = make_strm_func(
        client, 
        cid=args.cid, 
        save_dir=args.save_dir, 
        predicate=predicate, 
        base_url=args.base_url, 
        base_path=args.base_path,
        max_workers=args.max_workers, 
    )
    print(f"Total: {result['total']}")
    print(f"Count Upserts: {result['count_upserts']}")
    print(f"Count Ignores: {result['count_ignores']}")
    print(f"Count Removes: {result['count_removes']}")
    print(f"Count Errors: {result['count_errors']}")
    print(f"Elapsed Seconds: {result['elapsed_seconds']}")
