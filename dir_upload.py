from pathlib import Path
from p115client import *
from p115client.tool import *

client = P115Client(Path("~/115-cookies.txt").expanduser())
#client.login_another_open(100195123, replace=True)

# TODO: 这里填一个文件的路径
path = "test.txt"

upload_data = multipart_upload_init(
    client,
    path,
    pid = 0,
    filename = "",
    upload_data = None,
)
if "_upload_" in upload_data:
    partsize = upload_data["partsize"]
    part_number_next = upload_data["part_number_next"]
    with open(path, "rb") as file:
        if part_number_next > 1:
            file.seek(partsize * (part_number_next - 1))
        for part_number in range(part_number_next, upload_data["part_count"] + 1):
            url, headers = multipart_upload_url(client, upload_data, part_number)
            ## TODO: 你可以自己改写上传的逻辑
            ## NOTE: 使用 urllib3
            # from urllib3 import request
            # request("PUT", url, body=file.read(partsize), headers=headers)
            ## NOTE: 使用 requests
            # from requests import request
            # request("PUT", url, data=file.read(partsize), headers=headers)
            client.request(url=url, method="PUT", data=file.read(partsize), headers=headers, parse=False)
    resp = multipart_upload_complete(client, upload_data)
else:
    resp = upload_data
print(resp)