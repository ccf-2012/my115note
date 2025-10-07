from p115client import P115Client
from p115tiny302 import make_application
from uvicorn import run
from pathlib import Path


if __name__ == "__main__":

    # cookies = "UID=...; CID=...; SEID=...; KID=..."
    # client = P115Client(cookies, ensure_cookies=True, check_for_relogin=True)
    client = P115Client(Path("./115-cookies.txt").expanduser(), check_for_relogin=True)
    run(
        make_application(client, debug=False), 
        host="::", 
        port=5245, 
        proxy_headers=True, 
        server_header=False, 
        forwarded_allow_ips="*", 
        timeout_graceful_shutdown=1, 
    )

