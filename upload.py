from pathlib import Path
from p115client import P115Client
from p115client.tool import P115MultipartUpload

client = P115Client(Path("~/115-cookies.txt").expanduser())

# NOTE: 待上传文件的路径（同样也支持 URL）
path = "/path/to/file"

uploader = P115MultipartUpload.from_path(path, user_id=client.user_id, user_key=client.user_key)
# NOTE: 返回字典说明秒传成功
if isinstance(uploader, dict):
    print(uploader)
else:
    from os.path import getsize
    # NOTE: 你可以随意指定其它各种进度条模块，或者自己写的函数
    from tqdm import tqdm

    # NOTE: 文件总大小需要你自己获取，`reporthook`只做增量推送
    with tqdm(total=getsize(path), unit="B", unit_scale=True, desc="Uploading") as t:
        # NOTE: `iter_upload` 支持其它请求模块，例如 urllib3
        #     from urllib3_request import request
        #     uploader.iter_upload(request=request)
        for _ in uploader.iter_upload(reporthook=t.update):
            pass
    print(uploader.complete())

