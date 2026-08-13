#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 simulation/screens/native 下竖屏(170x320)截图的关键像素 (新深蓝科技风 v4)"""
from PIL import Image
import os
import sys

def c565(v):
    r = (v >> 11) & 0x1F
    g = (v >> 5) & 0x3F
    b = v & 0x1F
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))

C = {k: c565(v) for k, v in {
    'BG': 0x1084, 'BG2': 0x1906, 'ROW_BG': 0x1968, 'HD_TOP': 0x441B, 'HD_MID': 0x32F5, 'HD_BOT': 0x19F0,
    'ACCENT': 0x2B36, 'MODEL_BG': 0x6061, 'MODEL_BG2': 0x4040, 'VALUE': 0x4EDF, 'LABEL': 0x8473, 'YELLOW': 0xFFE9,
    'GREEN': 0x07E0, 'GREEN_D': 0x0368, 'ORANGE': 0xFD20, 'RED': 0xF9E6,
    'WHITE': 0xFFFF, 'DIM': 0x8C71}.items()}
C['BLACK'] = (0, 0, 0)

N = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens", "native")


def px(im, x, y):
    return im.getpixel((x, y))


def count(im, box, color):
    return sum(1 for y in range(box[1], box[3]) for x in range(box[0], box[2]) if im.getpixel((x, y)) == color)


def load(name):
    return Image.open(os.path.join(N, name + ".png")).convert("RGB")


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)
    print("  ok:", msg)


# ---------- 01_home_empty ----------
im = load("01_home_empty")
check(im.size == (170, 320), "尺寸 170x320")
check(px(im, 2, 2) == C['HD_TOP'], "标题栏渐变-上")
check(px(im, 2, 12) == C['HD_MID'], "标题栏渐变-中")
check(px(im, 2, 20) == C['HD_BOT'], "标题栏渐变-下")
check(px(im, 85, 40) == C['BG2'], "状态卡底色(y26..98)")
check(px(im, 85, 104) == C['ROW_BG'], "空横幅底色(y102..130)")
check(count(im, (30, 102, 140, 130), C['DIM']) > 30, "未发现无人机文字")
check(count(im, (2, 292, 168, 312), C['VALUE']) > 10, "底部 CH 提示(青)")
check(count(im, (2, 292, 168, 312), C['YELLOW']) > 10, "底部 短按进入(黄)")

# ---------- 02_home ----------
im = load("02_home")
check(px(im, 85, 104) == C['GREEN_D'], "已发现-绿色横幅")
check(count(im, (30, 102, 140, 130), C['GREEN']) > 30, "横幅文字")
check(px(im, 2, 135) == C['ROW_BG'], "行1底色")
check(count(im, (26, 136, 168, 150), C['WHITE']) > 40, "行1机型文字(白)")
check(count(im, (26, 153, 110, 167), C['VALUE']) > 30, "行1 ID 青色")
check(count(im, (100, 292, 168, 312), C['YELLOW']) > 20, "底部 短按进入(黄)")
check(count(im, (146, 4, 168, 18), C['WHITE']) > 10, "电池图标")

# ---------- 03_list ----------
im = load("03_list")
check(px(im, 85, 62) == C['YELLOW'], "焦点行黄色(focus=1, y62)")
check(count(im, (2, 26, 168, 59), C['YELLOW']) < 400, "非焦点行非整块黄(仅序号徽章)")
check(count(im, (2, 62, 168, 95), C['YELLOW']) > 2800, "焦点行整块黄")
check(count(im, (2, 62, 168, 95), C['BLACK']) > 100, "焦点行黑色文字")
check(count(im, (2, 292, 168, 310), C['LABEL']) > 20, "底部提示")

# ---------- 04_list_scrolled ----------
im = load("04_list_scrolled")
check(px(im, 85, 242) == C['YELLOW'], "滚动后末行焦点(y242)")
check(count(im, (2, 26, 168, 59), C['YELLOW']) < 400, "滚动后首行非整块黄")

# ---------- 05_detail (分组信息流) ----------
im = load("05_detail")
check(count(im, (40, 26, 130, 46), C['WHITE']) > 60, "暗红横幅上的白色机型名")
check(px(im, 20, 28) == C['MODEL_BG'], "机型横幅暗红-上")
check(px(im, 20, 44) == C['MODEL_BG2'], "机型横幅暗红-下")
check(count(im, (4, 60, 166, 290), C['VALUE']) > 150, "数值行青色")
check(count(im, (2, 60, 100, 290), C['LABEL']) > 80, "标签行灰蓝")
check(count(im, (0, 288, 170, 320), C['YELLOW']) == 0, "底部无黄色操作条")
check(count(im, (2, 296, 168, 316), C['DIM']) > 20, "底部 短按:导航")

# ---------- 06_qr ----------
im = load("06_qr")
# QR 白框: ox=19, oy=90, scale=4, qrPx=132 → 白框 13..157 x 84..224; 青色描边在 11..159 x 82..226
check(px(im, 11, 100) == C['ACCENT'], "二维码青色描边")
check(px(im, 16, 88) == (255, 255, 255), "二维码白框")
w = b = 0
for y in range(90, 222):
    for x in range(19, 151):
        p = im.getpixel((x, y))
        if p == (255, 255, 255):
            w += 1
        elif p == (0, 0, 0):
            b += 1
check(w > 500 and b > 500, "二维码黑白模块 %d/%d" % (w, b))
check(px(im, 85, 300) == C['YELLOW'], "二维码页黄色返回条")
check(count(im, (0, 288, 170, 320), C['BLACK']) > 30, "返回详情黑字")

# ---------- 07_qr_nopos ----------
im = load("07_qr_nopos")
check(count(im, (20, 116, 150, 132), C['ORANGE']) > 30, "无位置橙色提示")
check(px(im, 85, 300) == C['YELLOW'], "无位置页黄色返回条")

# ---------- 08_detail_autel ----------
im = load("08_detail_autel")
check(count(im, (30, 26, 140, 46), C['WHITE']) > 50, "道通详情-横幅白字")
check(count(im, (0, 24, 170, 48), C['MODEL_BG']) > 1500, "道通详情-暗红横幅")

# ---------- 09_nav (导航选择页, 焦点在"飞机" y132..211) ----------
im = load("09_nav")
check(count(im, (8, 132, 162, 211), C['YELLOW']) > 2800, "聚焦框-飞机实心黄")
check(count(im, (8, 132, 162, 211), C['BLACK']) > 100, "聚焦框黑色文字")
check(count(im, (8, 36, 162, 115), C['YELLOW']) < 1500, "非聚焦框非整块黄")
check(count(im, (8, 36, 162, 115), C['YELLOW']) > 80, "非聚焦框黄色描边+文字")
check(count(im, (2, 282, 168, 300), C['LABEL']) > 20, "底部提示")

print("\n全部像素校验通过 ✓")
