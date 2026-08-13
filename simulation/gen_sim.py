#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T-Display-S3 RID Monitor 固件屏幕模拟器生成器 (v3 — 竖屏 170x320)
=============================================================
屏幕旋转 90° 竖屏布局, 全部页面竖向。从固件源码精确还原:
  - 解析 src/cn_font.h 真实 16x16 中文字库(与固件同源)
  - 复刻 src/ui.cpp v3 的全部绘制逻辑
  - 内置 DJI SN→型号 + MAC OUI→品牌 识别(与固件 drone_models.h 同表)
  - 输出: 各页面 PNG 截图 + 自包含交互式 simulator.html

用法: python gen_sim.py
输出: ../simulation/screens/*.png 与 ../simulation/simulator.html
"""
import os
import re
import json
import base64
import struct

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens")
NATIVE = os.path.join(OUT, "native")
os.makedirs(NATIVE, exist_ok=True)

FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"
FALLBACK_FONT = ImageFont.truetype(FONT_PATH, 16)

# ============================================================
# 1. 解析固件字库 cn_font.h
# ============================================================
def parse_cn_font():
    text = open(os.path.join(SRC, "cn_font.h"), encoding="utf-8").read()
    km = re.search(r"cn_keys\[[^\]]*\]\s*=\s*\{(.*?)\};", text, re.S)
    gm = re.search(r"cn_glyphs\[[^\]]*\]\s*=\s*\{(.*?)\};", text, re.S)
    keys = [int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", km.group(1))]
    gbytes = [int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", gm.group(1))]
    assert len(keys) * 32 == len(gbytes), "字库数据长度不一致"
    glyphs = {}
    for i, k in enumerate(keys):
        raw = gbytes[i * 32:(i + 1) * 32]
        rows = []
        for r in range(16):
            rows.append((raw[r * 2] << 8) | raw[r * 2 + 1])
        glyphs[k] = rows
    return glyphs


CN = parse_cn_font()


def utf8_key(ch):
    b = ch.encode("utf-8")
    return (b[0] << 16) | (b[1] << 8) | b[2]


def render_cjk_fallback(ch):
    img = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(img)
    bbox = FALLBACK_FONT.getbbox(ch)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (16 - w) // 2 - bbox[0]
    y = (16 - h) // 2 - bbox[1]
    d.text((x, y), ch, font=FALLBACK_FONT, fill=255)
    rows = []
    for row in range(16):
        b = 0
        for col in range(16):
            if img.getpixel((col, row)) > 100:
                b |= (0x8000 >> col)
        rows.append(b)
    return rows


def cjk_rows(ch):
    k = utf8_key(ch)
    if k in CN:
        return CN[k]
    return render_cjk_fallback(ch)


# ============================================================
# 2. ASCII 8x16 字库
# ============================================================
def build_ascii_font():
    font = ImageFont.truetype(FONT_PATH, 16)
    out = {}
    for code in range(32, 127):
        ch = chr(code)
        img = Image.new("L", (16, 16), 0)
        d = ImageDraw.Draw(img)
        d.text((0, 0), ch, font=font, fill=255)
        bbox = img.getbbox()
        if bbox is None:
            out[ch] = [0] * 16
            continue
        l, t, r, b = bbox
        w, h = r - l, b - t
        glyph = img.crop((l, t, r, b))
        if w > 8:
            nh = max(1, round(h * 8 / w))
            glyph = glyph.resize((8, nh), Image.NEAREST)
            w, h = 8, nh
        rows = []
        for row in range(16):
            bm = 0
            gy = row - (16 - h) // 2
            if 0 <= gy < h:
                for col in range(8):
                    gx = col - (8 - w) // 2
                    if 0 <= gx < w and glyph.getpixel((gx, gy)) > 100:
                        bm |= (0x80 >> col)
            rows.append(bm)
        out[ch] = rows
    return out


ASCII = build_ascii_font()

# ============================================================
# 3. 配色(RGB565 -> RGB888, 与 ui.cpp 一致)
# ============================================================
def c565(v):
    r = (v >> 11) & 0x1F
    g = (v >> 5) & 0x3F
    b = v & 0x1F
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


C_BG        = c565(0x1084)
C_BG2       = c565(0x1906)
C_ROW_BG    = c565(0x1968)
C_HD_TOP    = c565(0x441B)
C_HD_MID    = c565(0x32F5)
C_HD_BOT    = c565(0x19F0)
C_ACCENT    = c565(0x2B36)
C_MODEL_BG  = c565(0x6061)
C_MODEL_BG2 = c565(0x4040)
C_VALUE     = c565(0x4EDF)
C_LABEL     = c565(0x8473)
C_YELLOW    = c565(0xFFE9)
C_GREEN     = c565(0x07E0)
C_GREEN_D   = c565(0x0368)
C_ORANGE    = c565(0xFD20)
C_RED       = c565(0xF9E6)
C_WHITE    = c565(0xFFFF)
C_DIM      = c565(0x8C71)
C_BLACK    = (0, 0, 0)

SW, SH = 170, 320   # 竖屏 (rotation 0)

# ============================================================
# 4. 识别表(与固件 src/drone_models.h 同表)
# ============================================================
DJI_MODELS = [
    ("1581F8LQ", "Mavic 4 Pro"), ("1581F67Q", "Mavic 3 Pro"),
    ("1581F5Y8", "Mavic 3 Classic"), ("1581F45Q", "Mavic 3"),
    ("1581F895", "Air 3S"), ("1581F6N8", "Air 3"), ("1581F385", "Air 2S"),
    ("1581FANL", "Mini 5 Pro"), ("1581F9DE", "Mini 5 Pro"),
    ("1581F5QJ", "Mini 4 Pro"), ("1581F8C8", "Mini 4K"),
    ("1581F4XF", "Mini 3 Pro"), ("1581F6CD", "Mini 2 SE"),
    ("1581FA8J", "Avata 360"), ("1581FBV5", "Lito 1"), ("1581FB34", "Lito X1"),
    ("1581F6W8", "Avata 2"), ("1581F4CQ", "Avata"),
    ("1581FA6Q", "Neo 2"), ("1581F8A1", "Neo"),
    ("1581F3CQ", "FPV"), ("1581F7V2", "Flip"),
    ("1581F6H8", "Matrice 350 RTK"), ("1581F5BK", "Matrice 30"),
    ("1581F52Q", "Mavic 3E/3T"), ("1581F578", "Inspire 3"),
]

OUI_BRANDS = [
    (0x60, 0x60, 0x1F, 0xFF, "大疆"), (0x34, 0xD2, 0x62, 0xFF, "大疆"),
    (0xE4, 0x7A, 0x2C, 0xFF, "大疆"), (0x58, 0xB8, 0x58, 0xFF, "大疆"),
    (0x04, 0xA8, 0x5A, 0xFF, "大疆"), (0x8C, 0x58, 0x23, 0xFF, "大疆"),
    (0x0C, 0x9A, 0xE6, 0xFF, "大疆"), (0x88, 0x29, 0x85, 0xFF, "大疆"),
    (0x4C, 0x43, 0xF6, 0xFF, "大疆"), (0x9C, 0x5A, 0x8A, 0xFF, "大疆"),
    (0xEC, 0x72, 0xF7, 0xFF, "大疆"), (0x34, 0x91, 0xF0, 0xFF, "大疆"),
    (0x18, 0xD7, 0x93, 0x6, "道通"), (0xEC, 0x5B, 0xCD, 0xE, "道通"),
    (0x00, 0x26, 0x7E, 0xFF, "Parrot"), (0x00, 0x12, 0x1C, 0xFF, "Parrot"),
    (0x90, 0x03, 0xB7, 0xFF, "Parrot"), (0xA0, 0x14, 0x3D, 0xFF, "Parrot"),
    (0x90, 0x3A, 0xE6, 0xFF, "Parrot"),
    (0x38, 0x1D, 0x14, 0xFF, "Skydio"),
    (0x6C, 0xDF, 0xFB, 0xE, "飞米"), (0x98, 0xAA, 0xFC, 0x7, "哈博森"),
    (0xE0, 0xB6, 0xF5, 0x8, "昊翔"), (0xA4, 0x51, 0x29, 0xFF, "极飞"),
    (0x54, 0x7D, 0x40, 0xFF, "臻迪"), (0x00, 0x1C, 0x0A, 0xFF, "一电"),
    (0xB0, 0x30, 0xC8, 0xFF, "Teal"), (0x00, 0x0C, 0xBF, 0xFF, "Holy Stone"),
    (0xD4, 0xA0, 0xFB, 0xB, "Hover"), (0x24, 0xA1, 0x0D, 0x7, "Cyon"),
]


def dji_model_display(uas_id):
    best, bl = None, 0
    u = (uas_id or "").upper()
    for p, n in DJI_MODELS:
        if u.startswith(p) and len(p) > bl:
            best, bl = n, len(p)
    if best is None:
        return ""
    return best if best.upper().startswith("DJI") else "DJI " + best


def oui_brand_display(mac):
    for b0, b1, b2, b3, brand in OUI_BRANDS:
        if mac[0] == b0 and mac[1] == b1 and mac[2] == b2 and \
           (b3 == 0xFF or (mac[3] >> 4) == b3):
            return brand + "无人机"
    return ""


def resolve_model(uas_id, mac):
    m = dji_model_display(uas_id)
    if m:
        return m
    return oui_brand_display(mac)


# ============================================================
# 5. 屏幕绘制原语
# ============================================================
class TFT:
    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img, "RGBA")

    def fillScreen(self, c):
        self.d.rectangle([0, 0, SW - 1, SH - 1], fill=c)

    def fillRect(self, x, y, w, h, c):
        self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=c)

    def drawRect(self, x, y, w, h, c):
        self.d.rectangle([x, y, x + w - 1, y + h - 1], outline=c)

    def drawPixel(self, x, y, c):
        if 0 <= x < SW and 0 <= y < SH:
            self.img.putpixel((x, y), c)

    def drawFastHLine(self, x, y, w, c):
        self.d.rectangle([x, y, x + w - 1, y], fill=c)

    def drawChar(self, x, y, ch, scale=1):
        rows = ASCII.get(ch)
        if not rows:
            return
        for r in range(16):
            bm = rows[r]
            for col in range(8):
                if bm & (0x80 >> col):
                    if scale == 1:
                        self.drawPixel(x + col, y + r, self.cur_color)
                    else:
                        self.fillRect(x + col * scale, y + r * scale, scale, scale, self.cur_color)

    def setTextColor(self, c):
        self.cur_color = c

    def drawCjkGlyph(self, x, y, rows, color, scale=1):
        for r in range(16):
            bm = rows[r]
            for col in range(16):
                if bm & (0x8000 >> col):
                    if scale == 1:
                        self.drawPixel(x + col, y + r, color)
                    else:
                        self.fillRect(x + col * scale, y + r * scale, scale, scale, color)

    def drawCjkText(self, x, y, s, color, scale=1):
        self.cur_color = color
        for ch in s:
            if ord(ch) < 0x80:
                self.drawChar(x, y, ch, scale)
                x += 8 * scale
            else:
                self.drawCjkGlyph(x, y, cjk_rows(ch), color, scale)
                x += 16 * scale


def cjk_text_width(s, scale=1):
    w = 0
    for ch in s:
        w += 8 * scale if ord(ch) < 0x80 else 16 * scale
    return w


def truncate_ascii(s, max_w):
    """按像素宽截断(仅 ASCII, 避免切坏中文); 返回截断后字符串"""
    if not s:
        return s
    if ord(s[0]) < 0x80:
        cap = max_w // 8
        if cap < len(s):
            return s[:cap]
    return s


# ============================================================
# 6. 标签映射(与固件一致)
# ============================================================
def ua_type_label(t):
    return {0: "未声明", 1: "固定翼", 2: "直升机", 3: "旋翼机", 4: "垂直起降", 5: "扑翼机",
            6: "滑翔机", 7: "风筝", 8: "自由气球", 9: "系留气球", 10: "飞艇", 11: "伞降",
            12: "火箭", 13: "系留动力", 14: "地面障碍", 15: "其他",
            100: "微型", 101: "轻型", 102: "小型", 103: "中型", 104: "大型"}.get(t, "未知")


def format_bssid(mac):
    return ":".join("%02X" % b for b in mac)


# ============================================================
# 7. 页面绘制(镜像 ui.cpp v3 竖屏)
# ============================================================
def draw_battery_icon(tft, x, y, pct):
    w, h = 22, 11
    tft.drawRect(x, y, w, h, C_WHITE)
    tft.fillRect(x + w, y + 3, 2, h - 6, C_WHITE)
    if pct < 0:
        tft.drawRect(x + 1, y + 1, w - 2, h - 2, C_DIM)
        return
    fill = min(pct * (w - 4) // 100, w - 4)
    c = C_GREEN if pct > 50 else (C_YELLOW if pct > 20 else C_RED)
    tft.fillRect(x + 2, y + 2, fill, h - 4, c)


def draw_rssi_bars(tft, x, y, rssi, color, max_h):
    level = 4 if rssi >= -50 else 3 if rssi >= -60 else 2 if rssi >= -70 else 1 if rssi >= -80 else 0
    bar_w, gap = 4, 2
    base = y + max_h
    for i in range(4):
        h = max(max_h * (i + 1) // 4, 2)
        c = color if i < level else C_DIM
        tft.fillRect(x + i * (bar_w + gap), base - h, bar_w, h, c)


def draw_header(tft, title, right=None):
    tft.fillRect(0, 0, SW, 8, C_HD_TOP)
    tft.fillRect(0, 8, SW, 8, C_HD_MID)
    tft.fillRect(0, 16, SW, 8, C_HD_BOT)
    tft.drawFastHLine(0, 23, SW, C_ACCENT)
    tft.drawCjkText(2, 4, title, C_WHITE, 1)
    if right:
        w = cjk_text_width(right, 1)
        tft.drawCjkText(SW - w - 2, 4, right, C_VALUE, 1)


def draw_group_title(tft, y, t):
    tft.drawCjkText(4, y, t, C_LABEL, 1)
    x0 = 4 + cjk_text_width(t, 1) + 6
    tft.drawFastHLine(x0, y + 8, SW - x0 - 4, C_ACCENT)


def draw_field(tft, y, label, val, vc):
    lw = cjk_text_width(label, 1)
    max_vw = SW - 4 - lw - 4 - 4
    vb = val
    if cjk_text_width(vb, 1) > max_vw and ord(vb[0]) < 0x80:
        cap = max_vw // 8
        if cap < len(vb):
            vb = vb[:cap]
    tft.drawCjkText(4, y, label, C_LABEL, 1)
    tft.drawCjkText(SW - cjk_text_width(vb, 1) - 4, y, vb, vc, 1)


def draw_row(tft, y, idx, d, focused):
    tc = C_BLACK if focused else C_WHITE
    tft.fillRect(2, y, SW - 4, 34, C_YELLOW if focused else C_ROW_BG)
    if not focused:
        tft.drawFastHLine(2, y, SW - 4, C_ACCENT)
    # 序号徽章
    tft.fillRect(4, y + 3, 18, 18, C_BLACK if focused else C_BG2)
    tft.drawRect(4, y + 3, 18, 18, C_BLACK if focused else C_YELLOW)
    buf = "%d" % idx
    tft.setTextColor(C_YELLOW)
    tft.drawChar(7, y + 5, buf[0], 1)
    tft.drawChar(14, y + 5, buf[1] if len(buf) > 1 else ' ', 1)
    label = d["model"] if d["model"] else ua_type_label(d["uaType"])
    lbl = truncate_ascii(label, SW - 28 - 4)
    tft.drawCjkText(26, y + 2, lbl, tc, 1)
    r = "%ddBm" % d["rssi"]
    tw = len(r) * 8
    draw_rssi_bars(tft, SW - tw - 2 - 4 - 18, y + 19, d["rssi"], C_BLACK if focused else C_GREEN, 10)
    tft.drawCjkText(SW - tw - 2, y + 19, r, C_BLACK if focused else C_VALUE, 1)
    ident = d["uasId"][:10] if d["uasId"] else "未知"
    id_max = SW - tw - 4 - 18 - 4 - 6 - 4
    if id_max < 16:
        id_max = 16
    ident = truncate_ascii(ident, id_max)
    tft.drawCjkText(26, y + 19, ident, C_BLACK if focused else C_VALUE, 1)


def draw_home(tft, drones, batt_pct, channel):
    tft.fillScreen(C_BG)
    draw_header(tft, "RID侦测器", None)
    rx = SW - 2
    if batt_pct >= 0:
        draw_battery_icon(tft, rx - 22, 6, batt_pct)
        rx -= 27
        b = "%d%%" % batt_pct
        tft.drawCjkText(rx - len(b) * 8, 4, b, C_YELLOW, 1)
    else:
        tft.drawCjkText(rx - 24, 4, "USB", C_LABEL, 1)

    n = len(drones)
    # 状态卡(26..98)
    tft.fillRect(2, 26, SW - 4, 72, C_BG2)
    tft.drawRect(2, 26, SW - 4, 72, C_ACCENT)
    tft.fillRect(8, 34, 6, 6, C_GREEN if n > 0 else C_DIM)
    tft.drawCjkText(18, 30, "侦测中" if n > 0 else "待机中", C_GREEN if n > 0 else C_LABEL, 1)
    tft.drawCjkText(SW - 60, 30, "信道", C_LABEL, 1)
    ch = "CH:%d" % channel
    tft.drawCjkText(8, 56, ch, C_VALUE, 2)
    cnt = "%d" % n
    cnt_w = cjk_text_width(cnt, 2)
    tft.drawCjkText(SW - 8 - cnt_w - 16 - 2, 56, cnt, C_WHITE, 2)
    tft.drawCjkText(SW - 8 - 16, 60, "架", C_LABEL, 1)

    # 发现横幅(102..130)
    if n > 0:
        tft.fillRect(2, 102, SW - 4, 28, C_GREEN_D)
        s = "已发现无人机 %d 架" % n
        tft.drawCjkText((SW - cjk_text_width(s, 1)) // 2, 108, s, C_GREEN, 1)
    else:
        tft.fillRect(2, 102, SW - 4, 28, C_ROW_BG)
        tft.drawCjkText((SW - cjk_text_width("未发现无人机", 1)) // 2, 108, "未发现无人机", C_DIM, 1)

    rows = min(n, 4)
    for i in range(rows):
        draw_row(tft, 134 + i * 36, i + 1, drones[i], False)

    ch = "CH:%d" % channel
    tft.drawCjkText(2, 294, ch, C_VALUE, 1)
    tft.drawCjkText(SW - cjk_text_width("短按进入", 1) - 2, 294, "短按进入", C_YELLOW, 1)


def draw_list(tft, drones, focus, scroll):
    tft.fillScreen(C_BG)
    n = len(drones)
    draw_header(tft, "选择无人机(%d)" % n, "返回")
    if n == 0:
        tft.drawCjkText((SW - cjk_text_width("暂无无人机信号", 1)) // 2, 120, "暂无无人机信号", C_LABEL, 1)
        tft.drawCjkText((SW - cjk_text_width("B键返回", 1)) // 2, 220, "B键返回", C_DIM, 1)
        return
    vis_rows = 7
    focus = max(0, min(focus, n - 1))
    if focus < scroll:
        scroll = focus
    if focus >= scroll + vis_rows:
        scroll = focus - vis_rows + 1
    for i in range(vis_rows):
        idx = scroll + i
        if idx >= n:
            break
        draw_row(tft, 26 + i * 36, idx + 1, drones[idx], idx == focus)
    tft.drawCjkText(2, 294, "短按:下移", C_LABEL, 1)
    tft.drawCjkText(SW - cjk_text_width("长按:确认", 1) - 2, 294, "长按:确认", C_LABEL, 1)


def draw_detail(tft, d, batt_pct, channel, drone_count):
    tft.fillScreen(C_BG)
    r = "%ddBm" % d["rssi"]
    tw = len(r) * 8
    draw_header(tft, "无人机详情", None)
    draw_rssi_bars(tft, SW - tw - 2 - 4 - 16, 7, d["rssi"], C_GREEN, 10)
    tft.drawCjkText(SW - tw - 2, 4, r, C_VALUE, 1)

    # 机型横幅(暗红渐变 24..52)
    tft.fillRect(0, 24, SW, 16, C_MODEL_BG)
    tft.fillRect(0, 40, SW, 12, C_MODEL_BG2)
    tft.drawFastHLine(0, 52, SW, C_RED)
    name = d["model"] if d["model"] else ua_type_label(d["uaType"])
    nm = truncate_ascii(name, SW - 4)
    tft.drawCjkText((SW - cjk_text_width(nm, 1)) // 2, 29, nm, C_WHITE, 1)

    y = 60
    # 组1: 标识
    draw_group_title(tft, y, "标识")
    y += 18
    ident = d["uasId"][:20] if d["uasId"] else "未知"
    draw_field(tft, y, "无人机ID", ident, C_VALUE)
    y += 18
    bssid = format_bssid(d["mac"])
    draw_field(tft, y, "BSSID", bssid, C_VALUE)
    y += 20
    # 组2: 位置
    draw_group_title(tft, y, "位置")
    y += 18
    draw_field(tft, y, "纬度", "%.5f" % d["aLat"] if d["hasAircraftPos"] else "--", C_VALUE)
    y += 18
    draw_field(tft, y, "经度", "%.5f" % d["aLon"] if d["hasAircraftPos"] else "--", C_VALUE)
    y += 18
    draw_field(tft, y, "高度", "%.0f m" % d["altGeo"] if d["altGeo"] > -999 else "--", C_VALUE)
    y += 18
    draw_field(tft, y, "速度", "%.1f m/s" % d["speedH"] if d["hasSpeed"] else "--", C_GREEN)
    y += 20
    # 组3: 监测
    draw_group_title(tft, y, "监测")
    y += 18
    draw_field(tft, y, "信道", "%d" % channel, C_VALUE)
    y += 18
    draw_field(tft, y, "无人机", "%d 架" % drone_count, C_GREEN)
    y += 18
    if batt_pct >= 0:
        draw_field(tft, y, "电量", "%d%%" % batt_pct, C_GREEN if batt_pct > 20 else C_RED)
    else:
        draw_field(tft, y, "电量", "USB", C_LABEL)
    y += 18
    proto = {0: "ASTM F3411 (WiFi)", 1: "国标 CN (WiFi)", 2: "BLE 广播"}.get(d.get("proto", 0), "ASTM F3411 (WiFi)")
    draw_field(tft, y, "协议", proto, C_LABEL)
    tft.drawCjkText(SW - cjk_text_width("短按:导航", 1) - 2, 300, "短按:导航", C_DIM, 1)


def draw_nav(tft, d, nav_target):
    tft.fillScreen(C_BG)
    draw_header(tft, "选择导航目标", None)
    box_x, box_w, box_h = 8, SW - 16, 80
    for i in range(2):
        y = 36 + i * 96
        foc = (nav_target == i)
        if foc:
            tft.fillRect(box_x, y, box_w, box_h, C_YELLOW)
            tft.fillRect(box_x, y, box_w, 3, C_BLACK)
        else:
            tft.fillRect(box_x, y, box_w, box_h, C_BG2)
            tft.drawRect(box_x, y, box_w, box_h, C_YELLOW)
        label = "导航到飞手" if i == 0 else "导航到飞机"
        tc = C_BLACK if foc else C_YELLOW
        # 左侧大图标块
        tft.fillRect(box_x + 10, y + 18, 20, 20, C_BLACK if foc else C_BG)
        tft.drawRect(box_x + 10, y + 18, 20, 20, tc)
        tft.fillRect(box_x + 17, y + 25, 6, 6, tc)
        tft.drawCjkText(box_x + 38, y + 12, label, tc, 1)
        have = d["hasOpPos"] if i == 0 else d["hasAircraftPos"]
        lat = d["opLat"] if i == 0 else d["aLat"]
        lon = d["opLon"] if i == 0 else d["aLon"]
        pos = "%.4f,%.4f" % (lat, lon) if have else "暂无位置"
        tft.drawCjkText(box_x + 38, y + 38, pos, C_BLACK if foc else C_VALUE, 1)
    tft.drawCjkText(2, 284, "短按:切换", C_LABEL, 1)
    tft.drawCjkText(SW - cjk_text_width("长按:出码", 1) - 2, 284, "长按:出码", C_LABEL, 1)


def wgs_to_gcj(lat, lon):
    """WGS-84 → GCJ-02(与固件 wgsToGcj 同算法), 高德导航二维码用"""
    if not (0.8293 <= lat <= 55.8271 and 72.004 <= lon <= 137.8347):
        return lat, lon
    import math
    a, ee = 6378245.0, 0.00669342162296594323
    x, y = lon - 105.0, lat - 35.0
    d_lat = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    d_lat += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    d_lat += (20.0*math.sin(y*math.pi) + 40.0*math.sin(y/3.0*math.pi)) * 2.0/3.0
    d_lat += (160.0*math.sin(y/12.0*math.pi) + 320.0*math.sin(y*math.pi/30.0)) * 2.0/3.0
    d_lon = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    d_lon += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    d_lon += (20.0*math.sin(x*math.pi) + 40.0*math.sin(x/3.0*math.pi)) * 2.0/3.0
    d_lon += (150.0*math.sin(x/12.0*math.pi) + 300.0*math.sin(x/30.0*math.pi)) * 2.0/3.0
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * math.pi)
    d_lon = (d_lon * 180.0) / (a / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lat + d_lat, lon + d_lon

def qr_matrix(url):
    import qrcode
    qr = qrcode.QRCode(version=None,
                       error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=1, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()


def draw_qr(tft, d, nav_target):
    tft.fillScreen(C_BG)
    draw_header(tft, ("飞手位置 二维码" if nav_target == 0 else "飞机位置 二维码"), None)
    have = d["hasOpPos"] if nav_target == 0 else d["hasAircraftPos"]
    lat = d["opLat"] if nav_target == 0 else d["aLat"]
    lon = d["opLon"] if nav_target == 0 else d["aLon"]
    if not have:
        tft.drawCjkText((SW - cjk_text_width("暂无该位置信息", 1)) // 2, 120, "暂无该位置信息", C_ORANGE, 1)
        tft.drawCjkText((SW - cjk_text_width("任意键返回", 1)) // 2, 220, "任意键返回", C_LABEL, 1)
        tft.fillRect(0, SH - 32, SW, 32, C_YELLOW)
        tft.drawCjkText((SW - cjk_text_width("返回详情", 1)) // 2, SH - 28, "返回详情", C_BLACK, 1)
        return None
    glat, glon = wgs_to_gcj(lat, lon)   # RID=WGS-84 → 高德 GCJ-02
    url = "https://uri.amap.com/marker?position=%1.6f,%1.6f" % (glon, glat)
    m = qr_matrix(url)
    size = len(m)
    avail_w, avail_h = SW - 16, SH - 24 - 40
    scale = max(min(avail_w // size, avail_h // size), 1)
    qr_px = size * scale
    ox = (SW - qr_px) // 2
    oy = 24 + (avail_h - qr_px) // 2 + 4
    tft.drawRect(ox - 8, oy - 8, qr_px + 16, qr_px + 16, C_ACCENT)
    tft.fillRect(ox - 6, oy - 6, qr_px + 12, qr_px + 12, C_WHITE)
    tft.fillRect(ox, oy, qr_px, qr_px, C_BLACK)
    for yy in range(size):
        for xx in range(size):
            if not m[yy][xx]:
                tft.fillRect(ox + xx * scale, oy + yy * scale, scale, scale, C_WHITE)
    pos = "%1.6f,%1.6f" % (lat, lon)
    tft.drawCjkText((SW - cjk_text_width(pos, 1)) // 2, 246, pos, C_YELLOW, 1)
    tft.fillRect(0, SH - 32, SW, 32, C_YELLOW)
    tft.drawCjkText((SW - cjk_text_width("返回详情", 1)) // 2, SH - 28, "返回详情", C_BLACK, 1)
    return {"size": size, "bits": "".join("1" if m[y][x] else "0" for y in range(size) for x in range(size))}


# ============================================================
# 8. 示例无人机数据(真实 DJI SN 前缀 / IEEE OUI)
# ============================================================
def mac(s):
    return [int(x, 16) for x in s.split(":")]


def make_drones():
    raw = [
        # uasId, uaType, rssi, alt, speed(m/s), op, ac, mac
        ("1581F45QK9C2D12", 101, -55, 120.5, 8.2, (39.9042, 116.4074), (39.9112, 116.4210), "AA:BB:CC:00:11:22"),
        ("1581FANL1M5P000", 100, -58, 60.0, 5.1, (39.9125, 116.4380), (39.9188, 116.4512), "AA:BB:CC:33:44:55"),
        ("1581F67Q3PRO000", 101, -62, 85.0, 15.4, (39.8878, 116.3760), (39.8830, 116.3705), "AA:BB:CC:66:77:88"),
        ("1581F895AIR3S00", 101, -67, 150.0, 9.8, (39.9210, 116.4155), (39.9301, 116.4288), "AA:BB:CC:99:AA:BB"),
        ("1581F8A1NEODR0N0", 100, -71, 30.0, 3.1, (39.8995, 116.4500), (39.9022, 116.4590), "AA:BB:CC:CC:DD:EE"),
        ("AUTEL-EVO2-0101", 101, -76, 95.0, 6.5, (39.8950, 116.4100), (39.9020, 116.4250), "18:D7:93:6A:0B:0C"),
        ("FIMI-X8SE-0001", 101, -82, 40.0, 4.2, (39.9100, 116.4300), (39.9160, 116.4430), "6C:DF:FB:EA:00:01"),
        ("1581F578INSPIRE3", 104, -88, -1000.0, 0.0, None, None, "AA:BB:CC:FF:00:11"),
        ("1581F5QJMINI4P0", 100, -52, 45.0, 7.5, (39.9080, 116.4120), (39.9140, 116.4260), "AA:BB:CC:12:34:56"),
        ("1581F385AIR2S00", 101, -64, 110.0, 11.0, (39.8930, 116.3820), (39.8990, 116.3950), "AA:BB:CC:78:9A:BC"),
        ("1581FA8JAVATA360", 101, -70, 55.0, 12.0, (39.9050, 116.4200), (39.9100, 116.4350), "AA:BB:CC:DE:F0:12"),
        ("1581F6H8M350RTK", 103, -59, 200.0, 13.5, (39.9000, 116.4050), (39.9080, 116.4180), "AA:BB:CC:34:56:78"),
        ("1581F4XFM3PRO00", 101, -66, 75.0, 6.0, (39.9150, 116.4400), (39.9210, 116.4530), "AA:BB:CC:9A:BC:DE"),
        ("1581F8C8MINI4K0", 100, -73, 35.0, 4.5, (39.9020, 116.4250), (39.9080, 116.4380), "AA:BB:CC:F0:12:34"),
        ("1581FB34LITOX100", 101, -79, 90.0, 8.0, (39.8970, 116.3900), (39.9030, 116.4030), "AA:BB:CC:56:78:9A"),
        ("PARROT-ANAFI-1", 101, -85, 70.0, 5.5, (39.9110, 116.4350), (39.9170, 116.4480), "00:26:7E:11:22:33"),
        ("SKYDIO-2-0001", 101, -90, 100.0, 9.0, (39.9060, 116.4150), (39.9120, 116.4280), "38:1D:14:44:55:66"),
        ("HOLY-S1-000001", 100, -93, 25.0, 2.5, (39.8980, 116.4450), (39.9040, 116.4580), "B4:CD:27:77:88:99"),
        ("HOVER-1-00001", 100, -88, 20.0, 3.0, (39.9090, 116.4200), (39.9150, 116.4330), "D4:A0:FB:AA:BB:CC"),
        ("CYON-RC-00001", 101, -91, 50.0, 6.5, (39.9030, 116.4300), (39.9090, 116.4430), "24:A1:0D:DD:EE:FF"),
        ("1581F3CQFPV0000", 101, -68, 130.0, 18.0, (39.8940, 116.3780), (39.9000, 116.3910), "AA:BB:CC:AB:CD:EF"),
        ("1581FA6QNEO2DRN0", 100, -57, 28.0, 4.0, (39.9130, 116.4370), (39.9190, 116.4500), "AA:BB:CC:FE:DC:BA"),
        ("1581F7V2FLIPDR0N", 101, -74, 42.0, 7.0, (39.9070, 116.4170), (39.9130, 116.4300), "AA:BB:CC:11:1A:2B"),
        ("UNKNOWN-DEVICE1", 101, -95, 0.0, 0.0, None, None, "01:02:03:04:05:06"),
    ]
    drones = []
    for uas_id, ua_type, rssi, alt, spd, op, ac, m in raw:
        d = dict(uasId=uas_id, uaType=ua_type, rssi=rssi, altGeo=alt, hasSpeed=True, speedH=spd,
                 hasOpPos=op is not None, opLat=op[0] if op else 0, opLon=op[1] if op else 0,
                 hasAircraftPos=ac is not None, aLat=ac[0] if ac else 0, aLon=ac[1] if ac else 0,
                 mac=mac(m))
        d["model"] = resolve_model(uas_id, d["mac"])
        if alt <= -999:
            d["altGeo"] = -1000
        if spd <= 0 and uas_id == "1581F578INSPIRE3":
            d["hasSpeed"] = False
        drones.append(d)
    return drones


def sort_by_rssi(drones):
    return sorted(drones, key=lambda d: -d["rssi"])


# ============================================================
# 9. 渲染 PNG
# ============================================================
def render(name, fn):
    img = Image.new("RGB", (SW, SH), C_BG)
    tft = TFT(img)
    fn(tft)
    img.save(os.path.join(NATIVE, name + ".png"))
    img.resize((SW * 3, SH * 3), Image.NEAREST).save(os.path.join(OUT, name + ".png"))
    print("  %s.png" % name)


def main_pngs():
    drones = sort_by_rssi(make_drones())
    print("渲染 PNG:")
    render("01_home_empty", lambda t: draw_home(t, [], -1, 11))
    render("02_home", lambda t: draw_home(t, drones, 78, 11))
    render("03_list", lambda t: draw_list(t, drones, 1, 0))
    render("04_list_scrolled", lambda t: draw_list(t, drones, 7, 1))
    render("05_detail", lambda t: draw_detail(t, dict(drones[0], idx=0), 78, 11, 24))
    render("06_qr", lambda t: draw_qr(t, drones[0], 1))
    render("07_qr_nopos", lambda t: draw_qr(t, next(d for d in drones if not d["hasAircraftPos"]), 1))
    render("08_detail_autel", lambda t: draw_detail(t, dict(next(d for d in drones if d["model"] == "道通无人机"), idx=0), 78, 11, 24))
    render("09_nav", lambda t: draw_nav(t, drones[0], 1))


# ============================================================
# 10. HTML 模拟器数据
# ============================================================
def pack_glyphs(rows_list):
    raw = bytearray()
    for rows in rows_list:
        for r in rows:
            raw += struct.pack(">H", r)
    return base64.b64encode(bytes(raw)).decode()


def build_html_data():
    drones = sort_by_rssi(make_drones())
    cn_keys = sorted(CN.keys())
    cn_glyphs = [CN[k] for k in cn_keys]
    ascii_chars = "".join(chr(c) for c in range(32, 127))
    ascii_glyphs = [ASCII[ch] for ch in ascii_chars]

    qr_map = {}
    for d in drones:
        entry = {}
        for target, (has, lat, lon) in ((0, (d["hasOpPos"], d["opLat"], d["opLon"])),
                                        (1, (d["hasAircraftPos"], d["aLat"], d["aLon"]))):
            if has:
                glat, glon = wgs_to_gcj(lat, lon)   # RID=WGS-84 → 高德 GCJ-02
                url = "https://uri.amap.com/marker?position=%1.6f,%1.6f" % (glon, glat)
                m = qr_matrix(url)
                size = len(m)
                entry[str(target)] = {"s": size,
                                      "b": "".join("1" if m[y][x] else "0" for y in range(size) for x in range(size))}
            else:
                entry[str(target)] = None
        qr_map[d["uasId"]] = entry

    used = set()
    for s in ["RID侦测器", "USB", "CH:", "已发现无人机 %d 架", "未发现无人机", "BUG反馈",
              "短按进入", "选择无人机(%d)", "B键:返回", "暂无无人机信号", "B键返回",
              "短按:下移", "长按:确认", "无人机详情", "无人机ID", "信号强度", "BSSID",
              "纬度", "经度", "高度", "速度", "信道:", "无人机:", "电量:", "短按:导航",
              "选择导航目标", "导航到飞手", "导航到飞机", "短按:切换", "长按:出码",
              "飞手位置 二维码", "飞机位置 二维码", "暂无该位置信息", "任意键返回",
              "返回详情", "暂无位置", "未知机型", "二维码生成失败"]:
        for ch in s:
            if ord(ch) >= 0x80:
                used.add(ch)
    for v in [ua_type_label(t) for t in list(range(16)) + list(range(100, 105))]:
        for ch in v:
            if ord(ch) >= 0x80:
                used.add(ch)
    missing = [ch for ch in used if utf8_key(ch) not in CN]
    if missing:
        print("警告: 以下字符不在固件字库中,将用同算法渲染:", missing)

    return {
        "cn_keys": cn_keys,
        "cn_glyphs_b64": pack_glyphs(cn_glyphs),
        "ascii_b64": pack_glyphs(ascii_glyphs),
        "qr": qr_map,
    }


# ============================================================
# 11. 生成 simulator.html (竖屏 170x320)
# ============================================================
def build_html(data):
    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>T-Display-S3 · RID 侦测器 v1.0 · 屏幕模拟器 (竖屏)</title>
<style>
  :root { --bg:#14161a; --panel:#1d2127; --line:#2c323b; --txt:#d7dde6; --dim:#8a939e;
          --green:#00ff00; --amber:#ffb300; --red:#ff3b30; --blue:#4da3ff; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--txt);
         font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif; padding:24px; }
  h1 { font-size:18px; margin-bottom:4px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  h1 .badge { font-size:11px; color:#9aa4b2; font-weight:normal; background:var(--panel);
              border:1px solid var(--line); padding:2px 8px; border-radius:10px; }
  .sub { color:var(--dim); font-size:12px; margin-bottom:18px; }
  .layout { display:flex; gap:22px; flex-wrap:wrap; align-items:flex-start; }
  .device { background:linear-gradient(180deg,#2a2d33,#202329); border:1px solid #000;
            border-radius:18px; padding:18px 20px 20px; box-shadow:0 10px 30px rgba(0,0,0,.5),
             inset 0 1px 0 rgba(255,255,255,.06); }
  .device .brand { font-size:11px; color:#8b95a3; letter-spacing:2px; margin-bottom:10px;
                   display:flex; justify-content:space-between; }
  .bezel { background:#000; border-radius:8px; padding:14px; border:1px solid #111;
           box-shadow: inset 0 0 24px rgba(0,0,0,.9); }
  canvas#lcd { width:340px; height:640px; image-rendering:pixelated; display:block;
               background:#000; border-radius:2px; }
  .keys { display:flex; gap:26px; margin-top:16px; justify-content:center; align-items:center; }
  .key { width:74px; height:40px; border-radius:8px; border:none; cursor:pointer;
         background:linear-gradient(180deg,#4a4f58,#33373e); color:#cfd6e0; font-weight:bold;
         font-size:13px; box-shadow:0 4px 0 #17191d, 0 6px 10px rgba(0,0,0,.4);
         transition:transform .05s, box-shadow .05s; user-select:none; font-family:inherit; }
  .key small { display:block; font-weight:normal; font-size:10px; color:#98a2b0; }
  .key:active, .key.pressed { transform:translateY(4px); box-shadow:0 0 0 #17191d, 0 2px 6px rgba(0,0,0,.4); }
  .key.hold { background:linear-gradient(180deg,#3d5f8f,#2c4468); }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:12px;
           padding:16px 18px; min-width:300px; max-width:360px; }
  .panel h2 { font-size:13px; color:#aeb7c3; margin-bottom:12px; letter-spacing:1px; }
  .panel .row { margin-bottom:14px; }
  .panel .row > label { display:block; font-size:12px; color:var(--dim); margin-bottom:6px; }
  .btns { display:flex; gap:8px; flex-wrap:wrap; }
  .btn { border:1px solid var(--line); background:#262b33; color:var(--txt); border-radius:7px;
         padding:6px 12px; font-size:12px; cursor:pointer; font-family:inherit; transition:all .1s; }
  .btn:hover { background:#2e343e; }
  .btn.on { background:#1d3a2a; border-color:var(--green); color:var(--green); }
  .btn.warn.on { background:#3a2c1d; border-color:var(--amber); color:var(--amber); }
  .btn.danger.on { background:#3a1d1d; border-color:var(--red); color:var(--red); }
  .chips { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { font-size:11px; padding:4px 10px; border-radius:12px; background:#232833; color:var(--dim); }
  .chip b { color:var(--txt); }
  .hint { font-size:12px; line-height:1.9; color:#9aa4b2; }
  .hint b { color:var(--txt); }
  .hint .k { display:inline-block; background:#2c323b; border:1px solid #3a414d; border-radius:4px;
             padding:0 6px; font-family:Consolas,monospace; font-size:11px; }
  .state { font-size:12px; color:var(--dim); margin-top:4px; }
  .state b { color:var(--blue); }
  #log { margin-top:10px; font-size:11px; color:#5f6b78; font-family:Consolas,monospace;
         height:64px; overflow-y:auto; border-top:1px dashed var(--line); padding-top:6px; }
</style>
</head>
<body>
<h1>T-Display-S3 <span class="badge">LILYGO · ESP32-S3 · rotation 0 竖屏 170×320</span>
    <span class="badge">RID 侦测器 v1.0</span><span class="badge">屏幕模拟器</span></h1>
<div class="sub">像素级还原固件 UI(真实 16×16 中文字库 + 8×16 ASCII)· 全页面竖向布局 · 按键行为与固件状态机一致 · 数据为模拟示例</div>

<div class="layout">
  <div class="device">
    <div class="brand"><span>T-DISPLAY-S3 · 竖屏</span><span id="screenName">主页</span></div>
    <div class="bezel"><canvas id="lcd" width="170" height="320"></canvas></div>
    <div class="keys">
      <button class="key" id="keyA"><small>A · BOOT</small>单击/长按</button>
      <button class="key" id="keyB"><small>B · IO14</small>返回</button>
    </div>
    <div class="keys" style="margin-top:8px">
      <button class="btn" id="tAclick">A 单击</button>
      <button class="btn" id="tAlong">A 长按(0.8s)</button>
      <button class="btn" id="tBclick">B 单击</button>
    </div>
  </div>

  <div class="panel">
    <h2>模拟控制</h2>
    <div class="row"><label>场景(无人机数量)</label>
      <div class="btns" id="scenes">
        <button class="btn" data-n="0">无</button>
        <button class="btn" data-n="3">3 架</button>
        <button class="btn on" data-n="6">6 架</button>
        <button class="btn" data-n="8">8 架</button>
        <button class="btn" data-n="12">12 架</button>
        <button class="btn" data-n="24">24 架</button>
        <button class="btn" data-n="200">200 架</button>
      </div>
    </div>
    <div class="row"><label>本机电池(监测设备)</label>
      <div class="btns" id="battSel">
        <button class="btn" data-b="-1">USB 供电</button>
        <button class="btn on" data-b="78">78% 正常</button>
        <button class="btn" data-b="35">35% 偏低</button>
        <button class="btn danger" data-b="8">8% 低电</button>
      </div>
    </div>
    <div class="row"><label>实时行为</label>
      <div class="btns">
        <button class="btn on" id="tJitter">RSSI 实时抖动(500ms)</button>
        <button class="btn on" id="tChannel">信道轮询 CH:1→6→11→3→8→13</button>
      </div>
    </div>
    <div class="row"><label>当前状态</label>
      <div class="state" id="state">—</div>
      <div class="chips" id="chips" style="margin-top:8px"></div>
    </div>
    <div class="row"><label>操作说明(与固件一致)</label>
      <div class="hint">
        <span class="k">A 单击</span> 主页→列表 / 列表→下移 / 详情→选择导航目标 / 导航页→切换飞手飞机<br>
        <span class="k">A 长按</span> 列表→打开详情 / 导航页→确认出码<br>
        <span class="k">A 长按</span> 列表→打开详情 / 导航页→确认出码<br>
        <span class="k">B 单击</span> 返回上一页(主页时进入列表) / B 长按 屏幕亮灭<br>
        <span class="k">A</span> 单击立即响应(无双击判定延迟, 避免连按误触)<br>
        键盘:<span class="k">A</span> 单击 · <span class="k">S</span> 长按 · <span class="k">B</span> 返回
      </div>
    </div>
    <div id="log"></div>
  </div>
</div>

<script>
"use strict";
/* ================= 数据(由 gen_sim.py 注入) ================= */
const CN_KEYS = @@CN_KEYS@@;
const CN_GLYPHS_B64 = "@@CN_GLYPHS@@";
const ASCII_B64 = "@@ASCII@@";
const QR_MAP = @@QR_MAP@@;

const C = { BG:[16,17,33], BG2:[24,34,53], ROW_BG:[28,44,68], HD_TOP:[70,130,220], HD_MID:[50,95,175], HD_BOT:[30,60,130],
            ACCENT:[44,100,180], MODEL_BG:[96,12,8], MODEL_BG2:[66,8,6], VALUE:[72,219,255], LABEL:[130,142,158], YELLOW:[255,255,77],
            GREEN:[0,255,0], GREEN_D:[0,110,70], ORANGE:[255,166,0], RED:[255,60,50],
            WHITE:[255,255,255], DIM:[140,142,140], BLACK:[0,0,0] };
const SW=170, SH=320;

/* ================= 字库解码 ================= */
function b64ToU16(b64){ const raw=atob(b64); const out=new Uint16Array(raw.length/2);
  for(let i=0;i<out.length;i++) out[i]=(raw.charCodeAt(i*2)<<8)|raw.charCodeAt(i*2+1); return out; }
const CN_BITS = b64ToU16(CN_GLYPHS_B64);
const CN_MAP = new Map(); CN_KEYS.forEach((k,i)=>CN_MAP.set(k,i));
const AS_BITS = b64ToU16(ASCII_B64);
function asciiIdx(ch){ const c=ch.charCodeAt(0); return (c>=32&&c<127)?c-32:-1; }
const TE = new TextEncoder();
const glyphCache = new Map();
function makeGlyphCanvas(w,h,bits,stride){
  const cv=document.createElement("canvas"); cv.width=w; cv.height=h;
  const g=cv.getContext("2d"); g.fillStyle="#fff";
  for(let r=0;r<h;r++){ const row=bits[r]; for(let c=0;c<w;c++)
    if(row & (1<<(stride-1-c))) g.fillRect(c,r,1,1); }
  return cv;
}
function glyphCanvas(kind,idx,color){
  const ck=kind+":"+idx+":"+color;
  let cv=glyphCache.get(ck);
  if(cv) return cv;
  if(kind==='a'){ const base=idx*16; const rows=[]; for(let r=0;r<16;r++) rows.push(AS_BITS[base+r]);
    cv=makeGlyphCanvas(8,16,rows,8); }
  else { const base=idx*16; const rows=[]; for(let r=0;r<16;r++) rows.push(CN_BITS[base+r]);
    cv=makeGlyphCanvas(16,16,rows,16); }
  const tmp=document.createElement("canvas"); tmp.width=cv.width; tmp.height=cv.height;
  const t=tmp.getContext("2d"); t.drawImage(cv,0,0); t.globalCompositeOperation="source-in";
  t.fillStyle=color; t.fillRect(0,0,cv.width,cv.height);
  glyphCache.set(ck,tmp); return tmp;
}

/* ================= 模拟状态 ================= */
const S = {
  screen:"HOME", listFocus:0, listScroll:0, detailIdx:0, navTarget:0,
  battPct:78, channel:11, chIdx:0, jitter:true, channelCycle:true,
  drones:[], sceneN:6, dirty:true
};
const CHANNELS=[1,6,11,3,8,13];

function uaTypeLabel(t){
  const m={0:"未声明",1:"固定翼",2:"直升机",3:"旋翼机",4:"垂直起降",5:"扑翼机",6:"滑翔机",
           7:"风筝",8:"自由气球",9:"系留气球",10:"飞艇",11:"伞降",12:"火箭",13:"系留动力",
           14:"地面障碍",15:"其他",100:"微型",101:"轻型",102:"小型",103:"中型",104:"大型"};
  return m[t]||"未知";
}
function fmtBssid(mac){ return mac.map(b=>b.toString(16).toUpperCase().padStart(2,"0")).join(":"); }
function activeDrones(){ return [...S.drones].sort((a,b)=>b.rssi-a.rssi); }
function truncAscii(s,maxW){ if(!s) return s; if(s.charCodeAt(0)<128){ const cap=Math.floor(maxW/8); if(cap<s.length) return s.slice(0,cap);} return s; }

/* ================= 绘制 ================= */
const cv=document.getElementById("lcd"); const ctx=cv.getContext("2d");
function fillRect(x,y,w,h,c){ ctx.fillStyle="rgb("+c.join(",")+")"; ctx.fillRect(x,y,w,h); }
function drawRect(x,y,w,h,c){ ctx.strokeStyle="rgb("+c.join(",")+")"; ctx.lineWidth=1;
  ctx.strokeRect(x+0.5,y+0.5,w-1,h-1); }
function drawFastHLine(x,y,w,c){ ctx.fillStyle="rgb("+c.join(",")+")"; ctx.fillRect(x,y,w,1); }
function drawCjkText(x,y,s,color,scale){
  scale=scale||1;
  ctx.fillStyle="rgb("+color.join(",")+")";
  for(let i=0;i<s.length;i++){
    const c=s.charCodeAt(i);
    if(c<128){ const idx=asciiIdx(s[i]); if(idx>=0) ctx.drawImage(glyphCanvas('a',idx,ctx.fillStyle),x,y,8*scale,16*scale); x+=8*scale; }
    else { const b=TE.encode(s[i]); const k=(b[0]<<16)|(b[1]<<8)|b[2]; const gi=CN_MAP.get(k);
      if(gi!==undefined) ctx.drawImage(glyphCanvas('c',gi,ctx.fillStyle),x,y,16*scale,16*scale); x+=16*scale; }
  }
}
function textWidth(s,scale){ scale=scale||1; let w=0; for(const ch of s) w += (ch.charCodeAt(0)<128?8:16)*scale; return w; }

function drawBatteryIcon(x,y,pct){
  drawRect(x,y,22,11,C.WHITE); fillRect(x+22,y+3,2,5,C.WHITE);
  if(pct<0){ drawRect(x+1,y+1,20,9,C.DIM); return; }
  let fill=Math.floor(pct*18/100); if(fill>18)fill=18;
  const c=pct>50?C.GREEN:(pct>20?C.YELLOW:C.RED);
  fillRect(x+2,y+2,fill,7,c);
}
function drawRssiBars(x,y,rssi,color,maxH){
  const level=rssi>=-50?4:rssi>=-60?3:rssi>=-70?2:rssi>=-80?1:0;
  const base=y+maxH;
  for(let i=0;i<4;i++){ let h=Math.max(Math.floor(maxH*(i+1)/4),2);
    const c=i<level?color:C.DIM; fillRect(x+i*6,base-h,4,h,c); }
}
function drawHeader(title,right){
  fillRect(0,0,SW,8,C.HD_TOP); fillRect(0,8,SW,8,C.HD_MID); fillRect(0,16,SW,8,C.HD_BOT);
  drawFastHLine(0,23,SW,C.ACCENT);
  drawCjkText(2,4,title,C.WHITE);
  if(right){ const w=textWidth(right); drawCjkText(SW-w-2,4,right,C.VALUE); }
}
function drawGroupTitle(y,t){
  drawCjkText(4,y,t,C.LABEL);
  const x0=4+textWidth(t)+6; drawFastHLine(x0,y+8,SW-x0-4,C.ACCENT);
}
function drawField(y,label,val,vc){
  const lw=textWidth(label);
  const maxVW=SW-4-lw-4-4;
  let vb=val;
  if(textWidth(vb)>maxVW && vb.charCodeAt(0)<128){ const cap=Math.floor(maxVW/8); if(cap<vb.length) vb=vb.slice(0,cap); }
  drawCjkText(4,y,label,C.LABEL); drawCjkText(SW-textWidth(vb)-4,y,vb,vc);
}
function drawRow(y,idx,d,focused){
  const tc=focused?C.BLACK:C.WHITE;
  fillRect(2,y,SW-4,34,focused?C.YELLOW:C.ROW_BG);
  if(!focused) drawFastHLine(2,y,SW-4,C.ACCENT);
  fillRect(4,y+3,18,18,focused?C.BLACK:C.BG2);
  drawRect(4,y+3,18,18,focused?C.BLACK:C.YELLOW);
  const id=String(idx);
  ctx.fillStyle="rgb("+C.YELLOW.join(",")+")";
  const a0=asciiIdx(id[0]); if(a0>=0) ctx.drawImage(glyphCanvas('a',a0,ctx.fillStyle),7,y+5);
  const a1=id.length>1?asciiIdx(id[1]):-1; if(a1>=0) ctx.drawImage(glyphCanvas('a',a1,ctx.fillStyle),14,y+5);
  const label=truncAscii(d.model||uaTypeLabel(d.uaType),SW-28-4);
  drawCjkText(26,y+2,label,tc);
  const r=d.rssi+"dBm"; const tw=r.length*8;
  drawRssiBars(SW-tw-2-4-18,y+19,d.rssi,focused?C.BLACK:C.GREEN,10);
  drawCjkText(SW-tw-2,y+19,r,focused?C.BLACK:C.VALUE);
  let ident=d.uasId?d.uasId.slice(0,10):"未知";
  let idMax=SW-tw-4-18-4-6-4; if(idMax<16)idMax=16;
  ident=truncAscii(ident,idMax);
  drawCjkText(26,y+19,ident,focused?C.BLACK:C.VALUE);
}
function drawHome(){
  fillRect(0,0,SW,SH,C.BG);
  drawHeader("RID侦测器",null);
  let rx=SW-2;
  if(S.battPct>=0){ drawBatteryIcon(rx-22,6,S.battPct); rx-=27;
    const b=S.battPct+"%"; drawCjkText(rx-b.length*8,4,b,C.YELLOW); }
  else { drawCjkText(rx-24,4,"USB",C.LABEL); }
  const n=S.drones.length;
  fillRect(2,26,SW-4,72,C.BG2); drawRect(2,26,SW-4,72,C.ACCENT);
  fillRect(8,34,6,6,n>0?C.GREEN:C.DIM);
  drawCjkText(18,30,n>0?"侦测中":"待机中",n>0?C.GREEN:C.LABEL);
  drawCjkText(SW-60,30,"信道",C.LABEL);
  drawCjkText(8,56,"CH:"+S.channel,C.VALUE,2);
  const cnt=String(n);
  const cntW=textWidth(cnt,2);
  drawCjkText(SW-8-cntW-16-2,56,cnt,C.WHITE,2);
  drawCjkText(SW-8-16,60,"架",C.LABEL);
  if(n>0){ fillRect(2,102,SW-4,28,C.GREEN_D);
    const s="已发现无人机 "+n+" 架"; drawCjkText(Math.floor((SW-textWidth(s))/2),108,s,C.GREEN); }
  else { fillRect(2,102,SW-4,28,C.ROW_BG);
    drawCjkText(Math.floor((SW-textWidth("未发现无人机"))/2),108,"未发现无人机",C.LABEL); }
  const rows=Math.min(n,4);
  for(let i=0;i<rows;i++) drawRow(134+i*36,i+1,S.dronesSorted[i],false);
  drawCjkText(2,294,"CH:"+S.channel,C.VALUE);
  drawCjkText(SW-textWidth("短按进入")-2,294,"短按进入",C.YELLOW);
}
function drawList(){
  fillRect(0,0,SW,SH,C.BG);
  const n=S.drones.length;
  drawHeader("选择无人机("+n+")","返回");
  if(n===0){ drawCjkText(Math.floor((SW-textWidth("暂无无人机信号"))/2),120,"暂无无人机信号",C.LABEL);
    drawCjkText(Math.floor((SW-textWidth("B键返回"))/2),220,"B键返回",C.DIM); return; }
  const vis=7;
  if(S.listFocus<0)S.listFocus=0; if(S.listFocus>=n)S.listFocus=n-1;
  if(S.listFocus<S.listScroll)S.listScroll=S.listFocus;
  if(S.listFocus>=S.listScroll+vis)S.listScroll=S.listFocus-vis+1;
  for(let i=0;i<vis;i++){ const idx=S.listScroll+i; if(idx>=n)break;
    drawRow(26+i*36,idx+1,S.dronesSorted[idx],idx===S.listFocus); }
  drawCjkText(2,294,"短按:下移",C.LABEL); drawCjkText(SW-textWidth("长按:确认")-2,294,"长按:确认",C.LABEL);
}
function drawDetail(){
  const d=S.dronesSorted[S.detailIdx]; if(!d){ S.screen="HOME"; S.dirty=true; return; }
  fillRect(0,0,SW,SH,C.BG);
  const r=d.rssi+"dBm"; const tw=r.length*8;
  drawHeader("无人机详情",null);
  drawRssiBars(SW-tw-2-4-16,7,d.rssi,C.GREEN,10);
  drawCjkText(SW-tw-2,4,r,C.VALUE);
  fillRect(0,24,SW,16,C.MODEL_BG); fillRect(0,40,SW,12,C.MODEL_BG2);
  drawFastHLine(0,52,SW,C.RED);
  const name=truncAscii(d.model||uaTypeLabel(d.uaType),SW-4);
  drawCjkText(Math.floor((SW-textWidth(name))/2),29,name,C.WHITE);
  let y=60;
  drawGroupTitle(y,"标识"); y+=18;
  drawField(y,"无人机ID",d.uasId?d.uasId.slice(0,20):"未知",C.VALUE); y+=18;
  drawField(y,"BSSID",fmtBssid(d.mac),C.VALUE); y+=20;
  drawGroupTitle(y,"位置"); y+=18;
  drawField(y,"纬度",d.hasAircraftPos?d.aLat.toFixed(5):"--",C.VALUE); y+=18;
  drawField(y,"经度",d.hasAircraftPos?d.aLon.toFixed(5):"--",C.VALUE); y+=18;
  drawField(y,"高度",d.altGeo>-999?Math.round(d.altGeo)+" m":"--",C.VALUE); y+=18;
  drawField(y,"速度",d.hasSpeed?d.speedH.toFixed(1)+" m/s":"--",C.GREEN); y+=20;
  drawGroupTitle(y,"监测"); y+=18;
  drawField(y,"信道",String(S.channel),C.VALUE); y+=18;
  drawField(y,"无人机",S.drones.length+" 架",C.GREEN); y+=18;
  if(S.battPct>=0) drawField(y,"电量",S.battPct+"%",S.battPct>20?C.GREEN:C.RED);
  else drawField(y,"电量","USB",C.LABEL);
  y+=18;
  const protoTxt={0:"ASTM F3411 (WiFi)",1:"国标 CN (WiFi)",2:"BLE 广播"}[d.proto??0]||"ASTM F3411 (WiFi)";
  drawField(y,"协议",protoTxt,C.LABEL);
  drawCjkText(SW-textWidth("短按:导航")-2,300,"短按:导航",C.DIM);
}
function drawNav(){
  const d=S.dronesSorted[S.detailIdx]; if(!d){ S.screen="HOME"; S.dirty=true; return; }
  fillRect(0,0,SW,SH,C.BG);
  drawHeader("选择导航目标",null);
  const boxX=8,boxW=SW-16,boxH=80;
  for(let i=0;i<2;i++){
    const y=36+i*96; const foc=S.navTarget===i;
    if(foc){ fillRect(boxX,y,boxW,boxH,C.YELLOW); fillRect(boxX,y,boxW,3,C.BLACK); }
    else { fillRect(boxX,y,boxW,boxH,C.BG2); drawRect(boxX,y,boxW,boxH,C.YELLOW); }
    const label=i===0?"导航到飞手":"导航到飞机";
    const tc=foc?C.BLACK:C.YELLOW;
    fillRect(boxX+10,y+18,20,20,foc?C.BLACK:C.BG);
    drawRect(boxX+10,y+18,20,20,tc);
    fillRect(boxX+17,y+25,6,6,tc);
    drawCjkText(boxX+38,y+12,label,tc);
    const have=i===0?d.hasOpPos:d.hasAircraftPos;
    const lat=i===0?d.opLat:d.aLat, lon=i===0?d.opLon:d.aLon;
    const pos=have?lat.toFixed(4)+","+lon.toFixed(4):"暂无位置";
    drawCjkText(boxX+38,y+38,pos,foc?C.BLACK:C.VALUE);
  }
  drawCjkText(2,284,"短按:切换",C.LABEL);
  drawCjkText(SW-textWidth("长按:出码")-2,284,"长按:出码",C.LABEL);
}
function drawQr(){
  const d=S.dronesSorted[S.detailIdx]; if(!d){ S.screen="HOME"; S.dirty=true; return; }
  fillRect(0,0,SW,SH,C.BG);
  drawHeader(S.navTarget===0?"飞手位置 二维码":"飞机位置 二维码",null);
  const have=S.navTarget===0?d.hasOpPos:d.hasAircraftPos;
  const lat=S.navTarget===0?d.opLat:d.aLat, lon=S.navTarget===0?d.opLon:d.aLon;
  if(!have){ drawCjkText(Math.floor((SW-textWidth("暂无该位置信息"))/2),120,"暂无该位置信息",C.ORANGE);
    drawCjkText(Math.floor((SW-textWidth("任意键返回"))/2),220,"任意键返回",C.LABEL);
    fillRect(0,SH-32,SW,32,C.YELLOW);
    drawCjkText(Math.floor((SW-textWidth("返回详情"))/2),SH-28,"返回详情",C.BLACK); return; }
  const qr=QR_MAP[d.uasId]?.[String(S.navTarget)];
  if(!qr){ drawCjkText(Math.floor((SW-textWidth("二维码生成失败"))/2),120,"二维码生成失败",C.RED); return; }
  const size=qr.s;
  const availW=SW-16, availH=SH-24-40;
  let scale=Math.min(Math.floor(availW/size),Math.floor(availH/size)); if(scale<1)scale=1;
  const qrPx=size*scale;
  const ox=Math.floor((SW-qrPx)/2), oy=24+Math.floor((availH-qrPx)/2)+4;
  drawRect(ox-8,oy-8,qrPx+16,qrPx+16,C.ACCENT);
  fillRect(ox-6,oy-6,qrPx+12,qrPx+12,C.WHITE);
  fillRect(ox,oy,qrPx,qrPx,C.BLACK);
  for(let y=0;y<size;y++) for(let x=0;x<size;x++)
    if(qr.b[y*size+x]==="0") fillRect(ox+x*scale,oy+y*scale,scale,scale,C.WHITE);
  const pos=lat.toFixed(6)+","+lon.toFixed(6);
  drawCjkText(Math.floor((SW-textWidth(pos))/2),246,pos,C.YELLOW);
  fillRect(0,SH-32,SW,32,C.YELLOW);
  drawCjkText(Math.floor((SW-textWidth("返回详情"))/2),SH-28,"返回详情",C.BLACK);
}
function render(){
  S.dronesSorted=activeDrones();
  switch(S.screen){
    case "HOME": drawHome(); break;
    case "LIST": drawList(); break;
    case "DETAIL": drawDetail(); break;
    case "NAV": drawNav(); break;
    case "QR": drawQr(); break;
  }
  document.getElementById("screenName").textContent=
    {HOME:"主页",LIST:"列表",DETAIL:"详情",NAV:"导航选择",QR:"二维码"}[S.screen];
}

/* ================= 按键事件 ================= */
function handleEvent(ev){
  const n=S.drones.length;
  switch(S.screen){
    case "HOME":
      if(ev==="A_CLICK"||ev==="B_CLICK"){ S.screen="LIST"; S.listFocus=0; S.listScroll=0; S.dirty=true; }
      break;
    case "LIST":
      if(ev==="A_CLICK"){ if(n>0){ S.listFocus++; if(S.listFocus>=n)S.listFocus=0; S.dirty=true; } }
      else if(ev==="A_LONG"){ if(n>0&&S.listFocus<n){ S.detailIdx=S.listFocus;   // focus 即绝对索引
        S.navTarget=0; S.screen="DETAIL"; S.dirty=true; } }
      else if(ev==="B_CLICK"){ S.screen="HOME"; S.dirty=true; }
      break;
    case "DETAIL":
      if(ev==="A_CLICK"){ S.screen="NAV"; S.dirty=true; }
      else if(ev==="B_CLICK"){ S.screen="LIST"; S.dirty=true; }
      break;
    case "NAV":
      if(ev==="A_CLICK"){ S.navTarget^=1; S.dirty=true; }
      else if(ev==="A_LONG"){ S.screen="QR"; S.dirty=true; }
      else if(ev==="B_CLICK"){ S.screen="DETAIL"; S.dirty=true; }
      break;
    case "QR":
      S.screen="DETAIL"; S.dirty=true; break;
  }
  updateState();
}

/* ================= 按钮物理键 ================= */
let pressTimer=null, pressT0=0, longFired=false;
function keyDown(which){
  if(which==='B'){ handleEvent("B_CLICK"); return; }
  longFired=false; pressT0=Date.now();
  pressTimer=setTimeout(()=>{ if(!longFired){ longFired=true;
    document.getElementById("keyA").classList.add("hold");
    handleEvent("A_LONG"); } },800);
}
function keyUp(which){
  if(which==='B') return;
  clearTimeout(pressTimer);
  document.getElementById("keyA").classList.remove("hold");
  if(longFired){ longFired=false; return; }
  handleEvent("A_CLICK");   // 单击立即响应, 无双击判定延迟
}
const keyA=document.getElementById("keyA"), keyB=document.getElementById("keyB");
keyA.addEventListener("pointerdown",e=>{e.preventDefault(); keyA.classList.add("pressed"); keyDown('A');});
keyA.addEventListener("pointerup",e=>{e.preventDefault(); keyA.classList.remove("pressed"); keyUp('A');});
keyA.addEventListener("pointerleave",()=>{keyA.classList.remove("pressed"); clearTimeout(pressTimer); longFired=false;});
keyB.addEventListener("pointerdown",e=>{e.preventDefault(); keyB.classList.add("pressed");});
keyB.addEventListener("pointerup",e=>{e.preventDefault(); keyB.classList.remove("pressed"); keyDown('B');});
document.addEventListener("keydown",e=>{
  const k=e.key.toLowerCase();
  if(k==='a'){ if(e.repeat)return; keyDown('A'); }
  if(k==='s'){ handleEvent("A_LONG"); }
  if(k==='b'){ keyDown('B'); }
});
document.addEventListener("keyup",e=>{ if(e.key.toLowerCase()==='a') keyUp('A'); });
document.getElementById("tAclick").onclick=()=>handleEvent("A_CLICK");
document.getElementById("tAlong").onclick=()=>handleEvent("A_LONG");
document.getElementById("tBclick").onclick=()=>handleEvent("B_CLICK");

/* ================= 数据与场景 ================= */
function makeDrone(o){
  return Object.assign({uaType:100,uasId:"",model:"",rssi:-60,altGeo:-1000,hasSpeed:false,speedH:0,
    hasOpPos:false,opLat:0,opLon:0,hasAircraftPos:false,aLat:0,aLon:0,mac:[0,0,0,0,0,0]},o);
}
const ALL_DRONES=[
  makeDrone({uaType:101,uasId:"1581F45QK9C2D12",model:"DJI Mavic 3",rssi:-55,altGeo:120.5,hasSpeed:true,speedH:8.2,
    hasOpPos:true,opLat:39.9042,opLon:116.4074,hasAircraftPos:true,aLat:39.9112,aLon:116.4210,mac:[0xAA,0xBB,0xCC,0x00,0x11,0x22]}),
  makeDrone({uaType:100,uasId:"1581FANL1M5P000",model:"DJI Mini 5 Pro",rssi:-58,altGeo:60,hasSpeed:true,speedH:5.1,
    hasOpPos:true,opLat:39.9125,opLon:116.4380,hasAircraftPos:true,aLat:39.9188,aLon:116.4512,mac:[0xAA,0xBB,0xCC,0x33,0x44,0x55]}),
  makeDrone({uaType:101,uasId:"1581F67Q3PRO000",model:"DJI Mavic 3 Pro",rssi:-62,altGeo:85,hasSpeed:true,speedH:15.4,
    hasOpPos:true,opLat:39.8878,opLon:116.3760,hasAircraftPos:true,aLat:39.8830,aLon:116.3705,mac:[0xAA,0xBB,0xCC,0x66,0x77,0x88]}),
  makeDrone({uaType:101,uasId:"1581F895AIR3S00",model:"DJI Air 3S",rssi:-67,altGeo:150,hasSpeed:true,speedH:9.8,
    hasOpPos:true,opLat:39.9210,opLon:116.4155,hasAircraftPos:true,aLat:39.9301,aLon:116.4288,mac:[0xAA,0xBB,0xCC,0x99,0xAA,0xBB]}),
  makeDrone({uaType:100,uasId:"1581F8A1NEODR0N0",model:"DJI Neo",rssi:-71,altGeo:30,hasSpeed:true,speedH:3.1,
    hasOpPos:true,opLat:39.8995,opLon:116.4500,hasAircraftPos:true,aLat:39.9022,aLon:116.4590,mac:[0xAA,0xBB,0xCC,0xCC,0xDD,0xEE]}),
  makeDrone({uaType:101,uasId:"AUTEL-EVO2-0101",model:"道通无人机",rssi:-76,altGeo:95,hasSpeed:true,speedH:6.5,
    hasOpPos:true,opLat:39.8950,opLon:116.4100,hasAircraftPos:true,aLat:39.9020,aLon:116.4250,mac:[0x18,0xD7,0x93,0x6A,0x0B,0x0C]}),
  makeDrone({uaType:101,uasId:"FIMI-X8SE-0001",model:"飞米无人机",rssi:-82,altGeo:40,hasSpeed:true,speedH:4.2,
    hasOpPos:true,opLat:39.9100,opLon:116.4300,hasAircraftPos:true,aLat:39.9160,aLon:116.4430,mac:[0x6C,0xDF,0xFB,0xEA,0x00,0x01]}),
  makeDrone({uaType:104,uasId:"1581F578INSPIRE3",model:"DJI Inspire 3",rssi:-88,mac:[0xAA,0xBB,0xCC,0xFF,0x00,0x11]}),
  makeDrone({uaType:100,uasId:"1581F5QJMINI4P0",model:"DJI Mini 4 Pro",rssi:-52,altGeo:45,hasSpeed:true,speedH:7.5,
    hasOpPos:true,opLat:39.9080,opLon:116.4120,hasAircraftPos:true,aLat:39.9140,aLon:116.4260,mac:[0xAA,0xBB,0xCC,0x12,0x34,0x56]}),
  makeDrone({uaType:101,uasId:"1581F385AIR2S00",model:"DJI Air 2S",rssi:-64,altGeo:110,hasSpeed:true,speedH:11,
    hasOpPos:true,opLat:39.8930,opLon:116.3820,hasAircraftPos:true,aLat:39.8990,aLon:116.3950,mac:[0xAA,0xBB,0xCC,0x78,0x9A,0xBC]}),
  makeDrone({uaType:101,uasId:"1581FA8JAVATA360",model:"DJI Avata 360",rssi:-70,altGeo:55,hasSpeed:true,speedH:12,
    hasOpPos:true,opLat:39.9050,opLon:116.4200,hasAircraftPos:true,aLat:39.9100,aLon:116.4350,mac:[0xAA,0xBB,0xCC,0xDE,0xF0,0x12]}),
  makeDrone({uaType:103,uasId:"1581F6H8M350RTK",model:"DJI Matrice 350 RTK",rssi:-59,altGeo:200,hasSpeed:true,speedH:13.5,
    hasOpPos:true,opLat:39.9000,opLon:116.4050,hasAircraftPos:true,aLat:39.9080,aLon:116.4180,mac:[0xAA,0xBB,0xCC,0x34,0x56,0x78]}),
  makeDrone({uaType:101,uasId:"1581F4XFM3PRO00",model:"DJI Mavic 3 Pro",rssi:-66,altGeo:75,hasSpeed:true,speedH:6,
    hasOpPos:true,opLat:39.9150,opLon:116.4400,hasAircraftPos:true,aLat:39.9210,aLon:116.4530,mac:[0xAA,0xBB,0xCC,0x9A,0xBC,0xDE]}),
  makeDrone({uaType:100,uasId:"1581F8C8MINI4K0",model:"DJI Mini 4K",rssi:-73,altGeo:35,hasSpeed:true,speedH:4.5,
    hasOpPos:true,opLat:39.9020,opLon:116.4250,hasAircraftPos:true,aLat:39.9080,aLon:116.4380,mac:[0xAA,0xBB,0xCC,0xF0,0x12,0x34]}),
  makeDrone({uaType:101,uasId:"1581FB34LITOX100",model:"DJI Lito X1",rssi:-79,altGeo:90,hasSpeed:true,speedH:8,
    hasOpPos:true,opLat:39.8970,opLon:116.3900,hasAircraftPos:true,aLat:39.9030,aLon:116.4030,mac:[0xAA,0xBB,0xCC,0x56,0x78,0x9A]}),
  makeDrone({uaType:101,uasId:"PARROT-ANAFI-1",model:"Parrot无人机",rssi:-85,altGeo:70,hasSpeed:true,speedH:5.5,
    hasOpPos:true,opLat:39.9110,opLon:116.4350,hasAircraftPos:true,aLat:39.9170,aLon:116.4480,mac:[0x00,0x26,0x7E,0x11,0x22,0x33]}),
  makeDrone({uaType:101,uasId:"SKYDIO-2-0001",model:"Skydio无人机",rssi:-90,altGeo:100,hasSpeed:true,speedH:9,
    hasOpPos:true,opLat:39.9060,opLon:116.4150,hasAircraftPos:true,aLat:39.9120,aLon:116.4280,mac:[0x38,0x1D,0x14,0x44,0x55,0x66]}),
  makeDrone({uaType:100,uasId:"HOLY-S1-000001",model:"Holy Stone无人机",rssi:-93,altGeo:25,hasSpeed:true,speedH:2.5,
    hasOpPos:true,opLat:39.8980,opLon:116.4450,hasAircraftPos:true,aLat:39.9040,aLon:116.4580,mac:[0xB4,0xCD,0x27,0x77,0x88,0x99]}),
  makeDrone({uaType:100,uasId:"HOVER-1-00001",model:"Hover无人机",rssi:-88,altGeo:20,hasSpeed:true,speedH:3,
    hasOpPos:true,opLat:39.9090,opLon:116.4200,hasAircraftPos:true,aLat:39.9150,aLon:116.4330,mac:[0xD4,0xA0,0xFB,0xAA,0xBB,0xCC]}),
  makeDrone({uaType:101,uasId:"CYON-RC-00001",model:"Cyon无人机",rssi:-91,altGeo:50,hasSpeed:true,speedH:6.5,
    hasOpPos:true,opLat:39.9030,opLon:116.4300,hasAircraftPos:true,aLat:39.9090,aLon:116.4430,mac:[0x24,0xA1,0x0D,0xDD,0xEE,0xFF]}),
  makeDrone({uaType:101,uasId:"1581F3CQFPV0000",model:"DJI FPV",rssi:-68,altGeo:130,hasSpeed:true,speedH:18,
    hasOpPos:true,opLat:39.8940,opLon:116.3780,hasAircraftPos:true,aLat:39.9000,aLon:116.3910,mac:[0xAA,0xBB,0xCC,0xAB,0xCD,0xEF]}),
  makeDrone({uaType:100,uasId:"1581FA6QNEO2DRN0",model:"DJI Neo 2",rssi:-57,altGeo:28,hasSpeed:true,speedH:4,
    hasOpPos:true,opLat:39.9130,opLon:116.4370,hasAircraftPos:true,aLat:39.9190,aLon:116.4500,mac:[0xAA,0xBB,0xCC,0xFE,0xDC,0xBA]}),
  makeDrone({uaType:101,uasId:"1581F7V2FLIPDR0N",model:"DJI Flip",rssi:-74,altGeo:42,hasSpeed:true,speedH:7,
    hasOpPos:true,opLat:39.9070,opLon:116.4170,hasAircraftPos:true,aLat:39.9130,aLon:116.4300,mac:[0xAA,0xBB,0xCC,0x11,0x1A,0x2B]}),
  makeDrone({uaType:101,uasId:"UNKNOWN-DEVICE1",model:"",rssi:-95,mac:[0x01,0x02,0x03,0x04,0x05,0x06]}),
];
// 200 架压测场景: 程序化生成变体(固件 MAX_DRONES=200 容量验证)
(function(){
  const ms=["DJI Mavic 3","DJI Mini 4 Pro","DJI Air 3S","DJI Avata 2","DJI Neo","DJI FPV",
            "DJI Matrice 350 RTK","DJI Inspire 3","道通无人机","Parrot无人机","Skydio无人机","飞米无人机","未知机型"];
  for(let i=0;i<176;i++){
    const m=ms[i%ms.length];
    ALL_DRONES.push(makeDrone({uaType:100+(i%3), uasId:"SIM"+String(200+i).padStart(8,"0"), model:m,
      rssi:-40-(i%50), altGeo:30+((i*3)%200), hasSpeed:true, speedH:2+(i%15),
      hasOpPos:true, opLat:39.90+(i%20)*0.001, opLon:116.40+(i%20)*0.001,
      hasAircraftPos:true, aLat:39.905+(i%30)*0.001, aLon:116.41+(i%30)*0.001,
      mac:[0x02,0x00,0x00,(i>>16)&0xFF,(i>>8)&0xFF,i&0xFF]}));
  }
})();
function setScene(n){
  S.sceneN=n; S.drones=ALL_DRONES.slice(0,n).map(d=>({...d}));
  if(S.screen!=="HOME"&&S.drones.length===0){ S.screen="HOME"; }
  if(S.detailIdx>=S.drones.length)S.detailIdx=0;
  if(S.listFocus>=S.drones.length)S.listFocus=0;
  S.dirty=true; updateSceneBtns(); updateState(); log("场景切换: "+n+" 架无人机");
}
document.querySelectorAll("#scenes .btn").forEach(b=>{
  b.onclick=()=>{ setScene(+b.dataset.n); };
});
function updateSceneBtns(){ document.querySelectorAll("#scenes .btn").forEach(b=>{
  b.classList.toggle("on",+b.dataset.n===S.sceneN); }); }
document.querySelectorAll("#battSel .btn").forEach(b=>{
  b.onclick=()=>{ S.battPct=+b.dataset.b; S.dirty=true;
    document.querySelectorAll("#battSel .btn").forEach(x=>x.classList.toggle("on",x===b)); updateState(); };
});
document.getElementById("tJitter").onclick=function(){ S.jitter=!S.jitter; this.classList.toggle("on",S.jitter); };
document.getElementById("tChannel").onclick=function(){ S.channelCycle=!S.channelCycle; this.classList.toggle("on",S.channelCycle); };

/* ================= 周期刷新 ================= */
let lastTick=0,lastBatt=0;
function tick(now){
  if(now-lastTick>=500){
    lastTick=now;
    if(S.jitter){ for(const d of S.drones){
      const delta=Math.round(Math.random()*3)-1;
      d.rssi=Math.max(-95,Math.min(-40,d.rssi+delta)); } }
    if(S.channelCycle){ S.chIdx=(S.chIdx+1)%CHANNELS.length; S.channel=CHANNELS[S.chIdx]; }
    if(now-lastBatt>=2000&&S.battPct>=0){ lastBatt=now;
      S.battPct=Math.max(0,Math.min(100,S.battPct+Math.round(Math.random()*3)-1)); }
    if(S.screen!=="HOME"&&S.drones.length===0){ S.screen="HOME"; }
    if((S.screen==="DETAIL"||S.screen==="NAV")&&S.detailIdx>=S.drones.length){ S.detailIdx=0; }
    S.dirty=true;
  }
  if(S.dirty){ S.dirty=false; render(); }
  updateState();
  requestAnimationFrame(tick);
}

/* ================= 状态面板 ================= */
function updateState(){
  const chips=[];
  chips.push("屏幕: <b>"+{HOME:"主页",LIST:"列表",DETAIL:"详情",NAV:"导航选择",QR:"二维码"}[S.screen]+"</b>");
  chips.push("无人机: <b>"+S.drones.length+"</b>");
  chips.push("信道: <b>CH:"+S.channel+"</b>");
  chips.push("电池: <b>"+(S.battPct>=0?S.battPct+"%":"USB")+"</b>");
  chips.push("导航目标: <b>"+(S.navTarget===0?"飞手":"飞机")+"</b>");
  if(S.dronesSorted&&S.dronesSorted[S.detailIdx]){
    chips.push("详情机型: <b>"+(S.dronesSorted[S.detailIdx].model||"未知")+"</b>");
  }
  document.getElementById("chips").innerHTML=chips.map(c=>'<span class="chip">'+c+"</span>").join("");
  let hint="";
  if(S.screen==="HOME") hint="A 单击/ B → 进入列表";
  else if(S.screen==="LIST") hint="A 单击:下移 · A 长按:打开详情 · B:返回主页";
  else if(S.screen==="DETAIL") hint="A 单击:选择导航目标 · B:返回列表";
  else if(S.screen==="NAV") hint="A 单击:切换 飞手/飞机 · A 长按:出码 · B:返回详情";
  else hint="任意键:返回详情";
  document.getElementById("state").innerHTML="下一步: "+hint;
}
function log(s){ const el=document.getElementById("log");
  el.textContent="[模拟] "+s+(el.textContent?"\n"+el.textContent:""); }

/* ================= 启动 ================= */
setScene(6);
requestAnimationFrame(tick);
</script>
</body>
</html>
"""
    return html.replace("@@CN_KEYS@@", json.dumps(data["cn_keys"])) \
               .replace("@@CN_GLYPHS@@", data["cn_glyphs_b64"]) \
               .replace("@@ASCII@@", data["ascii_b64"]) \
               .replace("@@QR_MAP@@", json.dumps(data["qr"]))


# ============================================================
# main
# ============================================================
if __name__ == "__main__":
    main_pngs()
    data = build_html_data()
    html = build_html(data)
    out_html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulator.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print("simulator.html 已生成 (%.1f KB)" % (os.path.getsize(out_html) / 1024))
    print("完成。输出目录:", os.path.dirname(os.path.abspath(__file__)))
