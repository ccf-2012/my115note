from p115client import P115Client
from p115open302 import make_application
from uvicorn import run
from pathlib import Path

# 授权登录
# app_id = 100195125
# client = P115Client(Path("./115-cookies.txt").expanduser(), check_for_relogin=True)
# # client = P115Client(cookies, ensure_cookies=True, check_for_relogin=True)
# client.login_another_open(replace=True)
# 或者直接用 refresh_token
refresh_token = "n3uaf.2d0e0ae8285da721004a2f66c4f202c26d481ef657af6ee0379b09a44b739550.94413039918c31104b53a6542005ab506bedd2f9402c10287d49ed5c1bd2da31"
client = P115Client("", check_for_relogin=True)
client.refresh_token = refresh_token
client.refresh_access_token()

run(
    make_application(client, debug=False), 
    host="::", 
    port=5245, 
    proxy_headers=True, 
    server_header=False, 
    forwarded_allow_ips="*", 
    timeout_graceful_shutdown=1, 
)