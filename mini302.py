#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__version__ = (0, 0, 2)

from pathlib import Path
from p115client import P115Client
from p115client.tool import get_id_to_path

client = P115Client(Path("./115-cookies.txt").expanduser())

from blacksheep import json, redirect, Application, Request

app = Application(show_error_details=__debug__)

@app.router.route("/", methods=["GET", "HEAD"])
@app.router.route("/<path:name2>", methods=["GET", "HEAD"])
async def index(
    request: Request, 
    id: int = 0, 
    pickcode: str = "", 
    sha1: str = "", 
    name: str = "", 
    path: str = "", 
    name2: str = "", 
):
    if not pickcode:
        if id > 0:
            pickcode = client.to_pickcode(id)
        elif sha1:
            resp = await client.fs_shasearch(sha1, async_=True)
            if not resp["state"]:
                return json({"sha1": sha1, "resp": resp}, 404)
            pickcode = resp["data"]["pick_code"]
        elif name:
            payload = {"fc": 2, "limit": 16, "search_value": name, "type": 99}
            suffix = name.rpartition(".")[-1]
            if len(suffix) < 5 and suffix.isalnum() and suffix[0].isalpha():
                payload["suffix"] = suffix
            resp = await client.fs_search(payload, async_=True)
            if not resp["state"]:
                return json({"name": name, "resp": resp}, 404)
            for info in resp["data"]:
                if info["n"] == name and info.get("sha"):
                    pickcode = info["pc"]
                    break
        elif path:
            try:
                id = await get_id_to_path(client, path, ensure_file=True, async_=True)
                pickcode = client.to_pickcode(id)
            except FileNotFoundError:
                return json({"path": path, "error": "not found"}, 404)
        elif name2:
            if name2.startswith("/") or ">" in name2:
                try:
                    id = await get_id_to_path(client, name2, ensure_file=True, async_=True)
                    pickcode = client.to_pickcode(id)
                except FileNotFoundError:
                    return json({"path": name2, "error": "not found"}, 404)
            else:
                name = name2
                payload = {"fc": 2, "limit": 16, "search_value": name, "type": 99}
                suffix = name.rpartition(".")[-1]
                if len(suffix) < 5 and suffix.isalnum() and suffix[0].isalpha():
                    payload["suffix"] = suffix
                resp = await client.fs_search(payload, async_=True)
                if not resp["state"]:
                    return json({"name": name, "resp": resp}, 404)
                for info in resp["data"]:
                    if info["n"] == name and info.get("sha"):
                        pickcode = info["pc"]
                        break
        if not pickcode:
            return json({"name": name, "path": path or name2, "error": "not found"}, 500)
    user_agent = request.get_first_header(b"user-agent") or b""
    try:
        url = await client.download_url(
            pickcode, 
            headers={"user-agent": user_agent.decode("latin-1")}, 
            app="android", 
            async_=True, 
        )
    except (FileNotFoundError, IsADirectoryError):
        return json({"pickcode": pickcode, "error": "not found"}, 404)
    return redirect(url)

if __name__ == "__main__":
    from uvicorn import run

    run(app, host=None, port=5245)
