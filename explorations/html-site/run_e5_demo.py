"""E5 synthetic attach laboratory.

An E5 carrier must redeem a random capability URL once before browser reads
or conditional writes. Its cookie is HttpOnly/SameSite=Strict and specific to
that carrier, despite browser cookie hostname scope ignoring TCP port.
Each request also pins the live Core runtime identity.

This is NOT user authentication, Native WebView2 integration or production TLS.
"""
from __future__ import annotations

import argparse
import json
import time
import webbrowser
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor,ProxyHandler,Request,build_opener

from e5_owner import launch_e5_owner
from run_e1_demo import call_json


def client_with_cookies():
    return build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))


def request_client(opener,base: str,path: str,*,method="GET",body=None,etag=""):
    raw=json.dumps(body,ensure_ascii=False).encode("utf-8") if body is not None else None
    headers={"Accept":"application/json"}
    if raw is not None:
        headers["Content-Type"]="application/json"
    if etag:
        headers["If-Match"]=etag
    request=Request(base+path,data=raw,method=method,headers=headers)
    try:
        with opener.open(request,timeout=8) as response:
            payload=response.read()
            try: obj=json.loads(payload.decode("utf-8"))
            except ValueError: obj={"message":payload.decode("utf-8",errors="replace")}
            return response.status,obj,response.headers.get("ETag","")
    except HTTPError as exc:
        payload=exc.read()
        try: obj=json.loads(payload.decode("utf-8"))
        except ValueError: obj={"message":payload.decode("utf-8",errors="replace")}
        return exc.code,obj,exc.headers.get("ETag","")


def smoke_e5(owner):
    a,b=owner.url("web"),owner.url("desktop_surrogate")
    client_a,client_b=client_with_cookies(),client_with_cookies()
    private=f"/api/v1/candidates/{owner.cid}/action-plan"

    # Neither proxy is browseable without explicit attach.
    for url in (a,b):
        status,_,_=request_client(client_a,url,private)
        if status!=403:
            raise AssertionError("E5 exposure before attach: "+str(status))
    # Redeem each independent grant. The opener follows the 303 and stores
    # the HTTP-only cookie (never placed in the HTML/JavaScript data model).
    client_a.open(owner.attach_url("web"),timeout=8).read()
    client_b.open(owner.attach_url("desktop_surrogate"),timeout=8).read()
    for url,client in ((a,client_a),(b,client_b)):
        status,body,_=request_client(client,url,"/api/v1/runtime/info")
        if status!=200 or body.get("product")!="SRW":
            raise AssertionError("Authorized E5 carrier did not reach Core")
    # Host-only cookie is shared across loopback ports, but distinct cookie
    # names ensure that the wrong client cannot authenticate another carrier.
    fresh=client_with_cookies()
    status,_,_=request_client(fresh,a,private)
    if status!=403: raise AssertionError("An unauthenticated new client was admitted")

    current=request_client(client_a,a,private)
    if current[0]!=200 or not current[2]:
        raise AssertionError("E5 Action Plan missing pinned ETag")
    saved=request_client(client_a,a,private,method="PATCH",etag=current[2],body={
        "owner":"E5 authorized Web","reason":"temporary capability-checked shared Core"
    })
    if saved[0]!=200:
        raise AssertionError("Attached Web PATCH failed: "+str(saved[0]))
    observed=request_client(client_b,b,private)
    if observed[1].get("owner")!="E5 authorized Web":
        raise AssertionError("Second attached carrier missed shared Core mutation")

    # Old attach cookie stops being useful once the carrier is detached;
    # new attachment uses a completely fresh token.
    owner.detach("web")
    old_base=a
    owner.attach("web")
    new_a=owner.url("web")
    if request_client(client_a,new_a,private)[0]!=403:
        raise AssertionError("Old attach grant must not authorize new carrier")
    client_a=client_with_cookies()
    client_a.open(owner.attach_url("web"),timeout=8).read()
    if request_client(client_a,new_a,private)[1].get("owner")!="E5 authorized Web":
        raise AssertionError("Reattach failed to access authoritative shared data")
    if owner.core.poll() is not None:
        raise AssertionError("Core must survive carrier detach and reattach")
    if call_json(owner.api,private)["owner"]!="E5 authorized Web":
        raise AssertionError("Core did not retain committed business state")
    print("E5 smoke PASS: unauthorized blocked, scoped per-carrier attach, cross-client read/write, token rotation.",flush=True)


def main():
    parser=argparse.ArgumentParser(
        description="Synthetic-only E5 Core identity and carrier attach lab"
    )
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--open-browser",action="store_true")
    args=parser.parse_args()
    print("SRW E5: disposable Core with separate browser attach capabilities",flush=True)
    with launch_e5_owner() as owner:
        if args.smoke:
            smoke_e5(owner)
            return 0
        print("Two browser windows will be given separate short-lived attach URLs.",flush=True)
        print("These one-time URLs grant access to TEMPORARY synthetic data only.",flush=True)
        print("Do not share URL tokens. The E5 experiment is not official authorization.",flush=True)
        if args.open_browser:
            webbrowser.open(owner.attach_url("web"))
            webbrowser.open(owner.attach_url("desktop_surrogate"))
        try:
            while owner.core.poll() is None:
                time.sleep(.5)
            raise RuntimeError("E5 Core stopped unexpectedly; existing carriers must fail closed")
        except KeyboardInterrupt:
            print("\nShutting down temporary Core and browser carriers.",flush=True)
            return 0


if __name__=="__main__":
    raise SystemExit(main())
