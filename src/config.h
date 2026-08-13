#pragma once
// ============================================================
// RID 监测固件 配置文件
// ============================================================
#include <stdint.h>

#define FW_NAME       "RID Monitor"
#define FW_VER        "v1.0"

// ---------------- 板级引脚 (T-Display-S3) ----------------
#define PIN_LCD_BL      38   // 背光
#define PIN_LCD_POWER   15   // LCD 电源使能,必须拉高(USB 未接时屏幕才亮)
#define PIN_BUTTON_A    0    // BOOT 键
#define PIN_BUTTON_B    14   // 第二按键
#define PIN_BAT_VOLT    4    // 电池电压检测 (ADC, 1/2 分压)

// ---------------- RID 侦听 ----------------
// RSSI 过滤阈值:低于该值的数据包直接丢弃(单位 dBm)
#define RSSI_FILTER_DBM   (-90)
// 侦听信道(2.4G):按 RID 常见信道轮询
// 1/6/11 为主流, 补充 3/8/13 覆盖非默认信道(驻留时间不变, 一轮 6×800ms=4.8s)
#define RID_CHANNELS      {1, 6, 11, 3, 8, 13}
// 每个信道停留时间(ms)
#define CHANNEL_DWELL_MS  800
// 无人机超过该时间未更新视为离线(ms)
// 15s ≈ 3 轮信道轮询容错(6 信道 × 800ms), 消失响应快且不会误判
#define DRONE_TIMEOUT_MS  15000

// 导航二维码坐标转换: RID 广播坐标为 WGS-84(GPS 原始), 高德(含 uri.amap.com)
// 使用 GCJ-02(火星坐标), 不转换会偏移 300~600 米。1=转换(中国大陆推荐)
#define QR_COORD_CONVERT  1
// 最多同时跟踪的无人机数量
// 同时跟踪的无人机数量上限(超过时自动顶掉信号最弱的一台)
// 每台约 180B DRAM, 200 台 ≈ 36KB, RAM 总量余量充足
#define MAX_DRONES        200

// ---------------- 天线 ----------------
// 强制固定使用外部天线(绝不使用 AUTO 自动切换)。
// 说明:ESP32-S3-WROOM-1 模块本身没有 RF 切换开关
//   (WROOM-1 = 板载 PCB 天线固定;WROOM-1U = 外置天线固定)。
//
// ⚠ 重要:标准 T-Display-S3 (WROOM-1 无 RF 开关) 必须保持本项为 0!
//   若置 1, antenna.cpp 会调用 esp_wifi_set_ant_gpio() 把
//   ANT_SEL_GPIO0/1 (默认 GPIO14/15) 配置成天线选择输出——
//   GPIO15 正是 LCD 电源使能,会被拉低导致"屏幕闪一下即黑屏"!
//
// 只有你的板子/模块确实带天线切换 GPIO(如其他带 RF switch 的板子),
//   才置 1,并确认 ANT_SEL_GPIO0/1 不与 LCD/按键冲突。
#define FORCE_EXTERNAL_ANTENNA 0

// ---------------- 二维码导航 ----------------
// 0 = 高德地图(国内默认, position=经度,纬度)
// 1 = Google Maps (q=纬度,经度)
// 2 = geo URI (geo:纬度,经度)
#define NAV_URL_MODE 0
