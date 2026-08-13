#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧大屏页面自检脚本
=====================
对 display-server/ 下的页面做静态断言 + 内联 JS 语法检查,
确认关键功能(登录门控/陌生警报/白名单/高德修复)未在编辑中丢失。

用法:
    python verify.py          # 全部检查, 全绿退出码 0

依赖: 无(仅标准库); JS 语法检查需要 node(可选, 无 node 时跳过)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NODE_CANDIDATES = [
    r"C:\Users\19389\AppData\Local\hermes\node\node.exe",
    "node",
]
fails = []


def check(name, cond, extra=""):
    print(("  ok: " if cond else "FAIL: ") + name + ((" " + extra) if extra else ""))
    if not cond:
        fails.append(name)


def js_syntax(label, html):
    """提取内联 <script> 块, 逐个 node --check 语法检查(无 node 则跳过)"""
    node = next((n for n in NODE_CANDIDATES
                 if subprocess.run([n, "--version"], capture_output=True).returncode == 0), None)
    if node is None:
        print("  -- 未找到 node, 跳过 JS 语法检查 --")
        return
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    ok = True
    for i, js in enumerate(scripts):
        if not js.strip():
            continue
        fd, path = tempfile_path(".js")
        try:
            open(path, "w", encoding="utf-8").write(js)
            r = subprocess.run([node, "--check", path], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                check("%s script#%d JS 语法" % (label, i + 1), False, r.stderr.strip()[:150])
                ok = False
        finally:
            os.remove(path)
    check("%s 内联 JS 语法(%d 块)" % (label, len(scripts)), ok)


def tempfile_path(suffix):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="hermes-verify-")
    os.close(fd)
    return fd, path


def main():
    dash = open(os.path.join(HERE, "dashboard.html"), encoding="utf-8").read()
    demo = open(os.path.join(HERE, "demo.html"), encoding="utf-8").read()
    srv = open(os.path.join(HERE, "server.py"), encoding="utf-8").read()

    print("== dashboard.html ==")
    check("登录 DOM 齐全", all('id="%s"' % x in dash for x in
                               ("loginOverlay", "loginUser", "loginPass", "loginBtn", "loginErr")))
    check("AUTH admin/admin123", 'user: "admin"' in dash and 'pass: "admin123"' in dash)
    check("登录后才连数据(零请求门控)",
          "connectWS();" in dash.split("function enterApp")[1].split("function connectWS")[0] and
          dash.count("connectWS();") == 1)
    check("登录后才加载高德 + onload 初始化地图",
          "loadAMapScript();" in dash.split("function enterApp")[1].split("function connectWS")[0] and
          "s.onload = () => initMap();" in dash)
    check("高德配置缺失检测(key/jscode)", "amapCfgIssue" in dash and 'return "jscode"' in dash)
    check("WS hostname 兜底(file:// 修复)", 'location.hostname || "localhost"' in dash)
    check("WS 失败指引", "python server.py --port COMx" in dash)
    check("警报核心(检测/触发/红闪/声音/按钮)",
          all(x in dash for x in ("checkAlerts", "triggerAlert", "stopAlert",
                                  'body.classList.add("alert")', "playAlarm",
                                  'getElementById("alertAuth").onclick')))
    check("白名单(持久化/增删/UI)",
          'localStorage.getItem("rid_whitelist")' in dash and
          all(x in dash for x in ("whitelistAdd", "whitelistRemove",
                                  'id="wlAdd"', 'id="wlRemove"', 'class="shield"')))
    check("高德容错 + fitView 无参修复", "amapTry" in dash and "map.setFitView()" in dash)
    js_syntax("dash", dash)

    print("== demo.html ==")
    check("登录 DOM + AUTH", all('id="%s"' % x in demo for x in
                                 ("loginOverlay", "loginUser", "loginPass", "loginBtn")) and
          'pass: "admin123"' in demo)
    check("登录门控(load 不直接启动)", "enterApp();" in demo.split("window.addEventListener(\"load\"")[1] and
          "tickData();" not in demo.split("window.addEventListener(\"load\"")[1])
    check("警报全套(与正式版一致)", all(x in demo for x in
                                        ("checkAlerts", "triggerAlert", "stopAlert", "playAlarm")))
    check("tickData 接入警报", "checkAlerts(new Set(drones.keys()))" in demo)
    check("白名单 UI", all(x in demo for x in ("whitelistAdd", "whitelistRemove",
                                               'id="wlAdd"', 'id="wlRemove"', 'class="shield"')))
    check("高德分支保留", all(x in demo for x in ("tryInitAMap", "amap.setFitView()")))
    js_syntax("demo", demo)

    print("== server.py ==")
    check("列可用 COM 端口", "list_ports.comports()" in srv)
    check("未检测到端口提示", "未检测到" in srv and "当前可用串口" in srv)
    check("重试逻辑", "3 秒后重试" in srv)
    check("python 语法", subprocess.run([sys.executable, "-m", "py_compile",
                                         os.path.join(HERE, "server.py")],
                                        capture_output=True).returncode == 0)

    print("\n" + ("全部通过 ✓" if not fails else "失败项: " + ", ".join(fails)))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
