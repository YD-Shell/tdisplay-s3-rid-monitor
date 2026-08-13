#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RID 监测智慧大屏 - PC 端数据服务
=================================
从 T-Display-S3 固件的 COM 串口读取 JSON 快照, 通过 WebSocket 推送给
浏览器智慧大屏(dashboard.html), 并托管该页面。

用法:
  1) 用 USB 线连接 T-Display-S3 到电脑
  2) 查看串口号:  pio device list  (或设备管理器)
  3) 运行:        python server.py --port COM5
     演示模式(无设备时预览大屏):  python server.py --demo
  4) 浏览器打开:  http://localhost:8080/dashboard.html

依赖:  pip install pyserial websockets
"""
import argparse
import asyncio
import json
import math
import os
import random
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENTS = set()          # WebSocket 客户端集合
LOCK = threading.Lock()
MAIN_LOOP = None         # 主 asyncio loop(websockets 服务所在), 由 ws_server 设置


# ---------------------------------------------------------------
# 串口读取线程: 逐行解析固件 JSON 快照, 广播给 WebSocket 客户端
# ---------------------------------------------------------------
def serial_worker(port: str, baud: int):
    import serial
    try:
        from serial.tools import list_ports
        avail = [p.device for p in list_ports.comports()]
        print(f"[serial] 目标串口 {port} @ {baud}")
        if port not in avail:
            print(f"[serial] ⚠ 未检测到 {port}! 当前可用串口: {avail if avail else '(无)'}")
            print(f"[serial]   请确认设备已插好, 并用 --port 指定正确串口 (设备管理器可查)")
    except Exception:
        pass
    print("[serial] 等待/重试连接中... (Ctrl+C 退出)")
    while True:
        try:
            ser = serial.Serial(port, baud, timeout=1.0)
            print(f"[serial] ✅ 已连接 {port} (等待固件数据...)")
            while True:
                line = ser.readline()
                if not line:
                    continue
                text = line.decode("utf-8", errors="ignore").strip()
                if not text.startswith("{"):
                    continue
                try:
                    obj = json.loads(text)
                except Exception:
                    continue
                if obj.get("t") == "snap":
                    broadcast(text)
        except serial.SerialException as e:
            print(f"[serial] 连接失败: {e} -- 3 秒后重试...")
            time.sleep(3)
        except Exception as e:
            print(f"[serial] 异常: {e}")
            time.sleep(1)


# ---------------------------------------------------------------
# 演示模式: 无设备时模拟 8 架无人机数据, 与固件协议一致
# ---------------------------------------------------------------
DEMO_DRONES = [
    # mac, model, uasId, lat, lon, alt, spd, 方向(度), rssi
    ("AA:BB:CC:00:11:22", "DJI Mavic 3",      "1581F45QK9C2D12", 39.9112, 116.4210, 120.5, 8.2,  30, -55),
    ("AA:BB:CC:33:44:55", "DJI Mini 5 Pro",   "1581FANL1M5P000", 39.9188, 116.4512, 60.0,  5.1, 120, -58),
    ("AA:BB:CC:66:77:88", "DJI Mavic 3 Pro",  "1581F67Q3PRO000", 39.8830, 116.3705, 85.0, 15.4, 210, -62),
    ("AA:BB:CC:99:AA:BB", "DJI Air 3S",       "1581F895AIR3S00", 39.9301, 116.4288, 150.0, 9.8,  80, -67),
    ("AA:BB:CC:CC:DD:EE", "DJI Neo",          "1581F8A1NEODR0N0", 39.9022, 116.4590, 30.0,  3.1, 350, -71),
    ("18:D7:93:6A:0B:0C", "道通无人机",        "AUTEL-EVO2-0101", 39.9020, 116.4250, 95.0,  6.5, 160, -76),
    ("6C:DF:FB:EA:00:01", "飞米无人机",        "FIMI-X8SE-0001",  39.9160, 116.4430, 40.0,  4.2,  20, -82),
    ("AA:BB:CC:FF:00:11", "DJI Inspire 3",    "1581F578INSPIRE3", 39.9210, 116.4100, 200.0, 2.0, 270, -88),
]
# 每架无人机的飞手位置(演示: 无人机附近 300-800m)
DEMO_OPS = [(d[3] + random.uniform(-0.005, 0.005), d[4] + random.uniform(-0.005, 0.005)) for d in DEMO_DRONES]
DEMO_STATE = [dict(lat=d[3], lon=d[4], rssi=d[8]) for d in DEMO_DRONES]


def demo_worker(interval: float):
    print(f"[demo] 演示模式: {len(DEMO_DRONES)} 架模拟无人机, 每 {interval}s 推送")
    while True:
        snap = {"t": "snap", "n": len(DEMO_DRONES), "ch": random.choice([1, 6, 11]),
                "bat": random.randint(70, 92), "drones": []}
        for i, d in enumerate(DEMO_DRONES):
            st = DEMO_STATE[i]
            heading = random.uniform(0, 360) * math.pi / 180
            st["lat"] += math.cos(heading) * 0.00008
            st["lon"] += math.sin(heading) * 0.00008
            st["rssi"] = max(-95, min(-40, st["rssi"] + random.randint(-2, 2)))
            op = DEMO_OPS[i]
            drone = {
                "mac": d[0], "model": d[1], "id": d[2],
                "rssi": st["rssi"],
                "lat": round(st["lat"], 6), "lon": round(st["lon"], 6),
                "alt": d[5], "spd": d[6],
                "olat": round(op[0], 6), "olon": round(op[1], 6),
                "proto": 0,
            }
            snap["drones"].append(drone)
        broadcast(json.dumps(snap, ensure_ascii=False))
        time.sleep(interval)


# ---------------------------------------------------------------
# WebSocket 服务
# ---------------------------------------------------------------
async def ws_handler(ws, *args):
    CLIENTS.add(ws)
    print(f"[ws] 客户端接入 ({len(CLIENTS)} 个)")
    try:
        async for _ in ws:
            pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(ws)
        print(f"[ws] 客户端断开 ({len(CLIENTS)} 个)")


def broadcast(text: str):
    with LOCK:
        clients = list(CLIENTS)
    if not clients:
        return
    loop = MAIN_LOOP
    if loop is None or loop.is_closed():
        return
    for ws in clients:
        try:
            asyncio.run_coroutine_threadsafe(ws.send(text), loop)
        except Exception:
            pass


async def ws_server(host: str, port: int):
    global MAIN_LOOP
    import websockets
    MAIN_LOOP = asyncio.get_running_loop()
    async with websockets.serve(ws_handler, host, port):
        print(f"[ws] WebSocket 服务: ws://{host}:{port}")
        await asyncio.Future()  # 永远运行


# ---------------------------------------------------------------
# HTTP 托管(大屏页面)
# ---------------------------------------------------------------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def http_server(port: int):
    srv = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[http] 大屏页面: http://localhost:{port}/dashboard.html")
    srv.serve_forever()


# ---------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="RID 监测智慧大屏数据服务")
    ap.add_argument("--port", default="COM5", help="串口号 (默认 COM5)")
    ap.add_argument("--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--http", type=int, default=8080, help="页面 HTTP 端口 (默认 8080)")
    ap.add_argument("--ws", type=int, default=8765, help="WebSocket 端口 (默认 8765)")
    ap.add_argument("--demo", action="store_true", help="演示模式(无串口, 模拟无人机数据)")
    ap.add_argument("--interval", type=float, default=1.0, help="演示数据推送间隔秒 (默认 1.0)")
    args = ap.parse_args()

    print("=" * 56)
    print("  RID 监测智慧大屏 · 数据服务")
    print("=" * 56)

    threads = []
    if args.demo:
        threads.append(threading.Thread(target=demo_worker, args=(args.interval,), daemon=True))
    else:
        threads.append(threading.Thread(target=serial_worker, args=(args.port, args.baud), daemon=True))
    threads.append(threading.Thread(target=http_server, args=(args.http,), daemon=True))

    for t in threads:
        t.start()

    try:
        asyncio.run(ws_server("0.0.0.0", args.ws))
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
