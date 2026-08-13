#include "ui.h"
#include "config.h"
#include "drone_store.h"
#include "sniffer.h"
#include "buttons.h"
#include "cn_font.h"
#include "ascii_font.h"
#include <Arduino.h>
#include <stdio.h>
#include <string.h>
#include <esp_adc_cal.h>

extern "C" {
#include "qrcodegen/qrcodegen.h"
}

// ============================================================
// 屏幕: 170x320 (T-Display-S3, rotation 0 —— 旋转 90° 竖屏)
// 页面: HOME(主页) / LIST(二级菜单:选择无人机) / DETAIL(详情)
//       NAV(选择导航目标) / QR(二维码)
// 按键: A(IO0 BOOT) 单击=确认/切换  长按=进入/出码
//       B(IO14) 单击=返回  长按=屏幕亮灭
// 风格: 深蓝科技风 —— 渐变标题栏 + 状态卡 + 卡片列表 + 暗红机型
//       横幅 + 青色数值 + 黄色焦点; 全部页面竖向布局
// ============================================================

// ---------------- 配色 (RGB565, 由目标 RGB888 精确换算) ----------------
static const uint16_t C_BG       = 0x1084;  // 深蓝黑底 (16,17,33)
static const uint16_t C_BG2      = 0x1906;  // 卡片底   (24,34,53)
static const uint16_t C_ROW_BG   = 0x1968;  // 行底     (28,44,68)
static const uint16_t C_HD_TOP   = 0x441B;  // 标题栏渐变-上 (70,130,220)
static const uint16_t C_HD_MID   = 0x32F5;  // 标题栏渐变-中 (50,95,175)
static const uint16_t C_HD_BOT   = 0x19F0;  // 标题栏渐变-下 (30,60,130)
static const uint16_t C_ACCENT   = 0x2B36;  // 高光/描边蓝 (44,100,180)
static const uint16_t C_MODEL_BG = 0x6061;  // 机型横幅暗红-上 (96,12,8)
static const uint16_t C_MODEL_BG2= 0x4040;  // 机型横幅暗红-下 (66,8,6)
static const uint16_t C_VALUE    = 0x4EDF;  // 数值青色 (72,219,255)
static const uint16_t C_LABEL    = 0x8473;  // 标签灰蓝 (130,142,158)
static const uint16_t C_YELLOW   = 0xFFE9;  // 黄色 (255,255,77)
static const uint16_t C_GREEN    = 0x07E0;  // 绿
static const uint16_t C_GREEN_D  = 0x0368;  // 暗绿横幅底 (0,110,70)
static const uint16_t C_ORANGE   = 0xFD20;
static const uint16_t C_RED      = 0xF9E6;  // (255,60,50)
static const uint16_t C_WHITE    = 0xFFFF;
static const uint16_t C_DIM      = 0x8C71;  // 灰
static const uint16_t C_BLACK    = 0x0000;

// 竖屏尺寸
#define SW 170
#define SH 320

// ---------------- 屏幕状态 ----------------
typedef enum { SCR_HOME, SCR_LIST, SCR_DETAIL, SCR_NAV, SCR_QR } Screen;
static Screen g_screen = SCR_HOME;
static int g_listFocus = 0;    // LIST 焦点(相对可视区)
static int g_listScroll = 0;   // LIST 滚动
static int g_detailIdx = 0;    // DETAIL 对应 droneStoreGet 索引
static int g_navTarget = 0;    // 0=飞手 1=飞机
static uint32_t g_lastRefresh = 0;
static bool g_dirty = true;

// ---------------- 本机电池(监测设备电量) ----------------
static esp_adc_cal_characteristics_t s_adcChars;
static int s_battPct = -1;          // -1 = 未接电池(USB 供电); 0-100 = 电量百分比
static uint32_t g_lastBatt = 0;

static void battInit(void)
{
    esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_12, ADC_WIDTH_BIT_12, 1100, &s_adcChars);
    analogSetPinAttenuation(PIN_BAT_VOLT, ADC_11db);
}

// 每 2 秒采样一次电池电压(IO4, 1/2 分压)
static void battUpdate(void)
{
    uint32_t now = millis();
    if (now - g_lastBatt < 2000) return;
    g_lastBatt = now;
    uint32_t raw = analogRead(PIN_BAT_VOLT);
    uint32_t mv = esp_adc_cal_raw_to_voltage(raw, &s_adcChars) * 2;
    if (mv > 4300) { s_battPct = -1; return; }   // 未接电池时读到 TP4056 充电电压
    int pct = (int)((mv - 3300) * 100 / (4200 - 3300));
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    s_battPct = pct;
}

// 电池图标: 22x11 外壳 + 正极触点 + 按百分比填充(颜色随电量变化)
static void drawBatteryIcon(int x, int y, int pct)
{
    const int w = 22, h = 11;
    tft.drawRect(x, y, w, h, C_WHITE);
    tft.fillRect(x + w, y + 3, 2, h - 6, C_WHITE);
    if (pct < 0) { tft.drawRect(x + 1, y + 1, w - 2, h - 2, C_DIM); return; }
    int fill = (pct * (w - 4)) / 100;
    if (fill > w - 4) fill = w - 4;
    uint16_t c = (pct > 50) ? C_GREEN : ((pct > 20) ? C_YELLOW : C_RED);
    tft.fillRect(x + 2, y + 2, fill, h - 4, c);
}

// ---------------- CJK 16x16 字库绘制 ----------------
static int findGlyph(uint32_t key)
{
    int lo = 0, hi = CN_FONT_COUNT - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (cn_keys[mid] == key) return mid;
        if (cn_keys[mid] < key) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}

static uint32_t utf8Key(const char **pp)
{
    const uint8_t *p = (const uint8_t *)*pp;
    uint32_t k = ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | p[2];
    *pp += 3;
    return k;
}

static void drawCjkGlyph(int x, int y, uint32_t key, uint16_t color, int scale)
{
    int g = findGlyph(key);
    if (g < 0) return;
    const uint8_t *bits = cn_glyphs + g * CN_FONT_BYTES;
    for (int row = 0; row < 16; row++) {
        uint16_t b = ((uint16_t)bits[row * 2] << 8) | bits[row * 2 + 1];
        for (int col = 0; col < 16; col++) {
            if (b & (0x8000 >> col)) {
                if (scale == 1) tft.drawPixel(x + col, y + row, color);
                else tft.fillRect(x + col * scale, y + row * scale, scale, scale, color);
            }
        }
    }
}

static int cjkTextWidth(const char *s, int scale)
{
    int w = 0;
    while (*s) {
        if ((uint8_t)*s < 0x80) { w += 8 * scale; s++; }
        else { s += 3; w += 16 * scale; }
    }
    return w;
}

// 混合 ASCII(8x16 自绘字模)+ 中文(16x16) 文本
// ASCII 用内置 ASCII_GLYPHS 自绘, 不依赖 TFT_eSPI 字体系统
// (TFT_eSPI drawChar 在并行模式下部分屏幕批次会缺字/错乱)
static void drawAsciiGlyph(int x, int y, char ch, uint16_t color, int scale)
{
    int idx = (uint8_t)ch - 32;
    if (idx < 0 || idx >= ASCII_FONT_COUNT) return;
    const uint8_t *bits = ASCII_GLYPHS + idx * 16;
    for (int row = 0; row < 16; row++) {
        uint8_t b = bits[row];
        for (int col = 0; col < 8; col++) {
            if (b & (0x80 >> col)) {
                if (scale == 1) tft.drawPixel(x + col, y + row, color);
                else tft.fillRect(x + col * scale, y + row * scale, scale, scale, color);
            }
        }
    }
}

static void drawCjkText(int x, int y, const char *s, uint16_t color, int scale)
{
    while (*s) {
        if ((uint8_t)*s < 0x80) {
            drawAsciiGlyph(x, y, *s, color, scale);
            x += 8 * scale;
            s++;
        } else {
            uint32_t k = utf8Key(&s);
            drawCjkGlyph(x, y, k, color, scale);
            x += 16 * scale;
        }
    }
}

// ---------------- 标准信号柱状图 ----------------
static void drawRssiBars(int x, int y, int rssi, uint16_t color, int maxH)
{
    // 4 格: >=-50 满格, -60=3格, -70=2格, -80=1格, 更弱=0格(画暗柱)
    int level = 0;
    if (rssi >= -50) level = 4;
    else if (rssi >= -60) level = 3;
    else if (rssi >= -70) level = 2;
    else if (rssi >= -80) level = 1;
    const int barW = 4, gap = 2;
    int base = y + maxH;
    for (int i = 0; i < 4; i++) {
        int h = maxH * (i + 1) / 4;
        if (h < 2) h = 2;
        uint16_t c = (i < level) ? color : C_DIM;
        tft.fillRect(x + i * (barW + gap), base - h, barW, h, c);
    }
}

// ---------------- 文本标签 ----------------
static const char *uaTypeLabel(uint8_t t)
{
    switch (t) {
    case 0:   return "未声明";
    case 1:   return "固定翼";
    case 2:   return "直升机";
    case 3:   return "旋翼机";
    case 4:   return "垂直起降";
    case 5:   return "扑翼机";
    case 6:   return "滑翔机";
    case 7:   return "风筝";
    case 8:   return "自由气球";
    case 9:   return "系留气球";
    case 10:  return "飞艇";
    case 11:  return "伞降";
    case 12:  return "火箭";
    case 13:  return "系留动力";
    case 14:  return "地面障碍";
    case 15:  return "其他";
    case 100: return "微型";
    case 101: return "轻型";
    case 102: return "小型";
    case 103: return "中型";
    case 104: return "大型";
    default:  return "未知";
    }
}

static const char *idTypeLabel(uint8_t t)
{
    switch (t) {
    case 1: return "序列号";
    case 2: return "注册号";
    case 3: return "UTM编号";
    case 4: return "会话ID";
    default: return "无";
    }
}

static const char *statusLabel(uint8_t s)
{
    switch (s) {
    case 1: return "地面";
    case 2: return "空中";
    case 3: return "紧急";
    case 4: return "故障";
    default: return "未声明";
    }
}

static void formatPos(char *buf, int len, double lat, double lon)
{
    if (lat == 0 && lon == 0) snprintf(buf, len, "--");
    else snprintf(buf, len, "%1.4f,%1.4f", lat, lon);
}

static void formatBssid(char *buf, const uint8_t *mac)
{
    snprintf(buf, 20, "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

// ---------------- 通用组件 ----------------
// 蓝色渐变标题栏(24px) + 底部高光线
static void drawHeader(const char *title, const char *right)
{
    tft.fillRect(0, 0, SW, 8, C_HD_TOP);
    tft.fillRect(0, 8, SW, 8, C_HD_MID);
    tft.fillRect(0, 16, SW, 8, C_HD_BOT);
    tft.drawFastHLine(0, 23, SW, C_ACCENT);   // 高光底边
    drawCjkText(2, 4, title, C_WHITE, 1);
    if (right && right[0]) {
        int w = cjkTextWidth(right, 1);
        drawCjkText(SW - w - 2, 4, right, C_VALUE, 1);
    }
}

// 分组小标题: 文字 + 右侧横线
static void drawGroupTitle(int y, const char *t)
{
    drawCjkText(4, y, t, C_LABEL, 1);
    int x0 = 4 + cjkTextWidth(t, 1) + 6;
    tft.drawFastHLine(x0, y + 8, SW - x0 - 4, C_ACCENT);
}

// 字段行: 标签(左) + 数值(右对齐)
// 值超过剩余宽度时自动截断 ASCII 字符, 避免与标签重叠
static void drawField(int y, const char *label, const char *val, uint16_t vc)
{
    int lw = cjkTextWidth(label, 1);
    int maxVW = SW - 4 - lw - 4 - 4;   // 值最大可用宽度
    char vb[48];
    snprintf(vb, sizeof vb, "%s", val);
    if (cjkTextWidth(vb, 1) > maxVW && (uint8_t)vb[0] < 0x80) {
        int cap = maxVW / 8;
        if (cap < (int)strlen(vb)) vb[cap] = 0;
    }
    drawCjkText(4, y, label, C_LABEL, 1);
    drawCjkText(SW - cjkTextWidth(vb, 1) - 4, y, vb, vc, 1);
}

// ---------------- 页面绘制 ----------------
// 竖屏列表行(卡片式, 高34):
//   左侧序号徽章(20x18) + 机型(白)  行2: ID(青) + 信号柱 + dBm(青)
static void drawRow(int y, int idx, const DroneEntry *d, bool focused)
{
    uint16_t tc = focused ? C_BLACK : C_WHITE;
    tft.fillRect(2, y, SW - 4, 34, focused ? C_YELLOW : C_ROW_BG);
    if (!focused) tft.drawFastHLine(2, y, SW - 4, C_ACCENT);  // 顶部高光

    char buf[24];
    // 序号徽章
    snprintf(buf, sizeof buf, "%d", idx);
    tft.fillRect(4, y + 3, 18, 18, focused ? C_BLACK : C_BG2);
    tft.drawRect(4, y + 3, 18, 18, focused ? C_BLACK : C_YELLOW);
    drawAsciiGlyph(7, y + 5, buf[0], C_YELLOW, 1);
    drawAsciiGlyph(14, y + 5, buf[1] ? buf[1] : ' ', C_YELLOW, 1);

    // 机型 / 类型标签(截断到行宽)
    const char *label = d->model[0] ? d->model : uaTypeLabel(d->uaType);
    char lbl[24];
    snprintf(lbl, sizeof lbl, "%s", label);
    int maxL = SW - 28 - 4;
    if (cjkTextWidth(lbl, 1) > maxL) {
        if ((uint8_t)lbl[0] < 0x80) {
            int cap = maxL / 8;
            if (cap < (int)strlen(lbl)) lbl[cap] = 0;
        }
    }
    drawCjkText(26, y + 2, lbl, tc, 1);

    // 行2: ID + 信号柱 + dBm
    char r[12];
    snprintf(r, sizeof r, "%ddBm", d->rssiLast);
    int tw = (int)strlen(r) * 8;
    drawRssiBars(SW - tw - 2 - 4 - 18, y + 19, d->rssiLast, focused ? C_BLACK : C_GREEN, 10);
    drawCjkText(SW - tw - 2, y + 19, r, focused ? C_BLACK : C_VALUE, 1);
    char id[24];
    snprintf(id, sizeof id, "%.10s", d->uasId[0] ? d->uasId : "未知");
    int idMax = SW - tw - 4 - 18 - 4 - 6 - 4;
    if (idMax < 16) idMax = 16;
    if ((uint8_t)id[0] < 0x80) {
        int cap = idMax / 8;
        if (cap < (int)strlen(id)) id[cap] = 0;
    }
    drawCjkText(26, y + 19, id, focused ? C_BLACK : C_VALUE, 1);
}

static void drawHome(void)
{
    tft.fillScreen(C_BG);

    // 标题栏: 标题 + 右侧(电池)
    drawHeader("RID侦测器", NULL);
    int rx = SW - 2;
    if (s_battPct >= 0) {
        drawBatteryIcon(rx - 22, 6, s_battPct);
        rx -= 27;
        char b[8];
        snprintf(b, sizeof b, "%d%%", s_battPct);
        drawCjkText(rx - (int)strlen(b) * 8, 4, b, C_YELLOW, 1);
    } else {
        drawCjkText(rx - 24, 4, "USB", C_LABEL, 1);
    }

    int n = droneStoreActiveCount();

    // 状态卡(26..98)
    tft.fillRect(2, 26, SW - 4, 72, C_BG2);
    tft.drawRect(2, 26, SW - 4, 72, C_ACCENT);
    // 左上: 状态点 + 侦听中
    tft.fillRect(8, 34, 6, 6, n > 0 ? C_GREEN : C_DIM);
    drawCjkText(18, 30, n > 0 ? "侦测中" : "待机中", n > 0 ? C_GREEN : C_LABEL, 1);
    // 右上: 信道标签
    drawCjkText(SW - 60, 30, "信道", C_LABEL, 1);
    // 中左: 大 CH 数字
    char ch[16];
    snprintf(ch, sizeof ch, "CH:%d", snifferChannel());
    drawCjkText(8, 56, ch, C_VALUE, 2);   // scale 2 (32px 高)
    // 中右: 无人机计数(大数字 + 架字并排, 不重叠)
    char cnt[16];
    snprintf(cnt, sizeof cnt, "%d", n);
    int cntW = cjkTextWidth(cnt, 2);
    drawCjkText(SW - 8 - cntW - 16 - 2, 56, cnt, C_WHITE, 2);
    drawCjkText(SW - 8 - 16, 60, "架", C_LABEL, 1);

    // 发现横幅(102..130)
    if (n > 0) {
        tft.fillRect(2, 102, SW - 4, 28, C_GREEN_D);
        char s[24];
        snprintf(s, sizeof s, "已发现无人机 %d 架", n);
        drawCjkText((SW - cjkTextWidth(s, 1)) / 2, 108, s, C_GREEN, 1);
    } else {
        tft.fillRect(2, 102, SW - 4, 28, C_ROW_BG);
        drawCjkText((SW - cjkTextWidth("未发现无人机", 1)) / 2, 108, "未发现无人机", C_DIM, 1);
    }

    // 无人机列表(前 4)
    int rows = n < 4 ? n : 4;
    for (int i = 0; i < rows; i++) {
        const DroneEntry *d = droneStoreGet(i);
        if (!d) break;
        drawRow(134 + i * 36, i + 1, d, false);
    }

    // 底部
    snprintf(ch, sizeof ch, "CH:%d", snifferChannel());
    drawCjkText(2, 294, ch, C_VALUE, 1);
    drawCjkText(SW - cjkTextWidth("短按进入", 1) - 2, 294, "短按进入", C_YELLOW, 1);
}

static void drawList(void)
{
    tft.fillScreen(C_BG);
    int n = droneStoreActiveCount();
    char h[32];
    snprintf(h, sizeof h, "选择无人机(%d)", n);
    drawHeader(h, "返回");

    if (n == 0) {
        drawCjkText((SW - cjkTextWidth("暂无无人机信号", 1)) / 2, 120, "暂无无人机信号", C_LABEL, 1);
        drawCjkText((SW - cjkTextWidth("B键返回", 1)) / 2, 220, "B键返回", C_DIM, 1);
        return;
    }

    const int visRows = 7;
    if (g_listFocus < 0) g_listFocus = 0;
    if (g_listFocus >= n) g_listFocus = n - 1;
    if (g_listFocus < g_listScroll) g_listScroll = g_listFocus;
    if (g_listFocus >= g_listScroll + visRows) g_listScroll = g_listFocus - visRows + 1;

    for (int i = 0; i < visRows; i++) {
        int idx = g_listScroll + i;
        if (idx >= n) break;
        const DroneEntry *d = droneStoreGet(idx);
        if (!d) break;
        drawRow(26 + i * 36, idx + 1, d, (idx == g_listFocus));
    }

    // 底部提示
    drawCjkText(2, 294, "短按:下移", C_LABEL, 1);
    drawCjkText(SW - cjkTextWidth("长按:确认", 1) - 2, 294, "长按:确认", C_LABEL, 1);
}

static void drawDetail(void)
{
    const DroneEntry *d = droneStoreGet(g_detailIdx);
    if (!d) { g_screen = SCR_HOME; g_dirty = true; return; }

    tft.fillScreen(C_BG);

    // 标题栏: 标题 + 信号
    char r[12];
    snprintf(r, sizeof r, "%ddBm", d->rssiLast);
    int tw = (int)strlen(r) * 8;
    drawHeader("无人机详情", NULL);
    drawRssiBars(SW - tw - 2 - 4 - 16, 7, d->rssiLast, C_GREEN, 10);
    drawCjkText(SW - tw - 2, 4, r, C_VALUE, 1);

    // 机型横幅(暗红渐变, 28px)
    tft.fillRect(0, 24, SW, 16, C_MODEL_BG);
    tft.fillRect(0, 40, SW, 12, C_MODEL_BG2);
    tft.drawFastHLine(0, 52, SW, C_RED);   // 红色亮边
    const char *name = d->model[0] ? d->model : uaTypeLabel(d->uaType);
    char nm[24];
    snprintf(nm, sizeof nm, "%s", name);
    int maxN = SW - 4;
    if (cjkTextWidth(nm, 1) > maxN) {
        if ((uint8_t)nm[0] < 0x80) {
            int cap = maxN / 8;
            if (cap < (int)strlen(nm)) nm[cap] = 0;
        }
    }
    drawCjkText((SW - cjkTextWidth(nm, 1)) / 2, 29, nm, C_WHITE, 1);

    // 分组信息流
    char buf[64];
    int y = 60;

    // 组1: 标识
    drawGroupTitle(y, "标识");
    y += 18;
    snprintf(buf, sizeof buf, "%.20s", d->uasId[0] ? d->uasId : "未知");
    drawField(y, "无人机ID", buf, C_VALUE); y += 18;
    char bssid[20];
    formatBssid(bssid, d->mac);
    drawField(y, "BSSID", bssid, C_VALUE); y += 20;

    // 组2: 位置
    drawGroupTitle(y, "位置");
    y += 18;
    if (d->hasAircraftPos) snprintf(buf, sizeof buf, "%1.5f", d->aLat);
    else snprintf(buf, sizeof buf, "--");
    drawField(y, "纬度", buf, C_VALUE); y += 18;
    if (d->hasAircraftPos) snprintf(buf, sizeof buf, "%1.5f", d->aLon);
    else snprintf(buf, sizeof buf, "--");
    drawField(y, "经度", buf, C_VALUE); y += 18;
    if (d->altGeo > -999) snprintf(buf, sizeof buf, "%.0f m", d->altGeo);
    else snprintf(buf, sizeof buf, "--");
    drawField(y, "高度", buf, C_VALUE); y += 18;
    if (d->hasSpeed) snprintf(buf, sizeof buf, "%.1f m/s", d->speedH);
    else snprintf(buf, sizeof buf, "--");
    drawField(y, "速度", buf, C_GREEN); y += 20;

    // 组3: 监测
    drawGroupTitle(y, "监测");
    y += 18;
    snprintf(buf, sizeof buf, "%d", snifferChannel());
    drawField(y, "信道", buf, C_VALUE); y += 18;
    snprintf(buf, sizeof buf, "%d 架", droneStoreActiveCount());
    drawField(y, "无人机", buf, C_GREEN); y += 18;
    if (s_battPct >= 0) {
        snprintf(buf, sizeof buf, "%d%%", s_battPct);
        drawField(y, "电量", buf, (s_battPct > 20) ? C_GREEN : C_RED);
    } else {
        drawField(y, "电量", "USB", C_LABEL);
    }
    y += 18;
    // 协议来源: 0=ASTM WiFi 1=国标 CN WiFi 2=BLE
    snprintf(buf, sizeof buf, "%s",
             d->protocol == 1 ? "国标 CN (WiFi)" : d->protocol == 2 ? "BLE 广播" : "ASTM F3411 (WiFi)");
    drawField(y, "协议", buf, C_LABEL);

    // 底部提示
    drawCjkText(SW - cjkTextWidth("短按:导航", 1) - 2, 300, "短按:导航", C_DIM, 1);
}

// 导航选择二级页面: 飞手 / 飞机 两个大选项, 带位置预览
static void drawNav(void)
{
    const DroneEntry *d = droneStoreGet(g_detailIdx);
    if (!d) { g_screen = SCR_HOME; g_dirty = true; return; }

    tft.fillScreen(C_BG);
    drawHeader("选择导航目标", NULL);

    const int boxX = 8, boxW = SW - 16, boxH = 80;
    for (int i = 0; i < 2; i++) {
        int y = 36 + i * 96;
        bool foc = (g_navTarget == i);
        if (foc) {
            tft.fillRect(boxX, y, boxW, boxH, C_YELLOW);
            tft.fillRect(boxX, y, boxW, 3, C_BLACK);          // 顶部黑条点缀
        } else {
            tft.fillRect(boxX, y, boxW, boxH, C_BG2);
            tft.drawRect(boxX, y, boxW, boxH, C_YELLOW);
        }
        const char *label = (i == 0) ? "导航到飞手" : "导航到飞机";
        uint16_t tc = foc ? C_BLACK : C_YELLOW;
        // 左侧大图标块
        tft.fillRect(boxX + 10, y + 18, 20, 20, foc ? C_BLACK : C_BG);
        tft.drawRect(boxX + 10, y + 18, 20, 20, tc);
        tft.fillRect(boxX + 17, y + 25, 6, 6, tc);
        drawCjkText(boxX + 38, y + 12, label, tc, 1);
        // 位置预览(4 位小数) / 暂无位置
        double lat = 0, lon = 0;
        bool have = (i == 0) ? d->hasOpPos : d->hasAircraftPos;
        if (i == 0) { lat = d->opLat; lon = d->opLon; }
        else { lat = d->aLat; lon = d->aLon; }
        char pos[24];
        if (have) snprintf(pos, sizeof pos, "%1.4f,%1.4f", lat, lon);
        else snprintf(pos, sizeof pos, "暂无位置");
        drawCjkText(boxX + 38, y + 38, pos, foc ? C_BLACK : C_VALUE, 1);
    }

    // 底部提示
    drawCjkText(2, 284, "短按:切换", C_LABEL, 1);
    drawCjkText(SW - cjkTextWidth("长按:出码", 1) - 2, 284, "长按:出码", C_LABEL, 1);
}

// WGS-84 → GCJ-02(火星坐标) 转换
// RID 广播坐标为 WGS-84, 高德地图/导航(uri.amap.com)使用 GCJ-02,
// 中国大陆区域不转换会偏移 300~600 米。标准公开算法, 精度 ±2m。
static void wgsToGcj(double lat, double lon, double *outLat, double *outLon)
{
    // PI 由 Arduino.h 提供(宏)
    const double a = 6378245.0;
    const double ee = 0.00669342162296594323;
    *outLat = lat; *outLon = lon;
    if (lat < 0.8293 || lat > 55.8271 || lon < 72.004 || lon > 137.8347) return;  // 境外不转

    double x = lon - 105.0, y = lat - 35.0;
    double dLat = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*sqrt(fabs(x));
    dLat += (20.0*sin(6.0*x*PI) + 20.0*sin(2.0*x*PI)) * 2.0/3.0;
    dLat += (20.0*sin(y*PI) + 40.0*sin(y/3.0*PI)) * 2.0/3.0;
    dLat += (160.0*sin(y/12.0*PI) + 320.0*sin(y*PI/30.0)) * 2.0/3.0;
    double dLon = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*sqrt(fabs(x));
    dLon += (20.0*sin(6.0*x*PI) + 20.0*sin(2.0*x*PI)) * 2.0/3.0;
    dLon += (20.0*sin(x*PI) + 40.0*sin(x/3.0*PI)) * 2.0/3.0;
    dLon += (150.0*sin(x/12.0*PI) + 300.0*sin(x/30.0*PI)) * 2.0/3.0;

    double radLat = lat / 180.0 * PI;
    double magic = sin(radLat);
    magic = 1 - ee * magic * magic;
    double sqrtMagic = sqrt(magic);
    dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * PI);
    dLon = (dLon * 180.0) / (a / sqrtMagic * cos(radLat) * PI);
    *outLat = lat + dLat;
    *outLon = lon + dLon;
}

static void drawQr(void)
{
    const DroneEntry *d = droneStoreGet(g_detailIdx);
    if (!d) { g_screen = SCR_HOME; g_dirty = true; return; }

    tft.fillScreen(C_BG);
    drawHeader(g_navTarget == 0 ? "飞手位置 二维码" : "飞机位置 二维码", NULL);

    double lat = 0, lon = 0;
    bool have = (g_navTarget == 0) ? d->hasOpPos : d->hasAircraftPos;
    if (g_navTarget == 0) { lat = d->opLat; lon = d->opLon; }
    else { lat = d->aLat; lon = d->aLon; }

    if (!have) {
        drawCjkText((SW - cjkTextWidth("暂无该位置信息", 1)) / 2, 120, "暂无该位置信息", C_ORANGE, 1);
        drawCjkText((SW - cjkTextWidth("任意键返回", 1)) / 2, 220, "任意键返回", C_LABEL, 1);
        tft.fillRect(0, SH - 32, SW, 32, C_YELLOW);
        drawCjkText((SW - cjkTextWidth("返回详情", 1)) / 2, SH - 28, "返回详情", C_BLACK, 1);
        return;
    }

    // 生成导航 URL 并编码二维码
    char url[96];
#if NAV_URL_MODE == 0
    double glat = lat, glon = lon;
#if QR_COORD_CONVERT
    wgsToGcj(lat, lon, &glat, &glon);   // RID=WGS-84 → 高德 GCJ-02
#endif
    snprintf(url, sizeof url, "https://uri.amap.com/marker?position=%1.6f,%1.6f", glon, glat);
#elif NAV_URL_MODE == 1
    snprintf(url, sizeof url, "https://maps.google.com/?q=%1.6f,%1.6f", lat, lon);
#else
    snprintf(url, sizeof url, "geo:%1.6f,%1.6f", lat, lon);
#endif

    static uint8_t qr[qrcodegen_BUFFER_LEN_FOR_VERSION(10)];
    static uint8_t tmp[qrcodegen_BUFFER_LEN_FOR_VERSION(10)];
    bool ok = qrcodegen_encodeText(url, tmp, qr, qrcodegen_Ecc_MEDIUM,
                                   1, 10, qrcodegen_Mask_AUTO, true);
    if (!ok) {
        drawCjkText((SW - cjkTextWidth("二维码生成失败", 1)) / 2, 120, "二维码生成失败", C_RED, 1);
        return;
    }
    int size = qrcodegen_getSize(qr);
    int availW = SW - 16, availH = SH - 24 - 40;
    int scale = (availW / size < availH / size) ? availW / size : availH / size;
    if (scale < 1) scale = 1;
    int qrPx = size * scale;
    int ox = (SW - qrPx) / 2, oy = 24 + (availH - qrPx) / 2 + 4;

    // 白底 + 黑模块 + 青色描边
    tft.drawRect(ox - 8, oy - 8, qrPx + 16, qrPx + 16, C_ACCENT);
    tft.fillRect(ox - 6, oy - 6, qrPx + 12, qrPx + 12, C_WHITE);
    tft.fillRect(ox, oy, qrPx, qrPx, C_BLACK);
    for (int yy = 0; yy < size; yy++)
        for (int xx = 0; xx < size; xx++)
            if (!qrcodegen_getModule(qr, xx, yy))
                tft.fillRect(ox + xx * scale, oy + yy * scale, scale, scale, C_WHITE);

    // 坐标
    char pos[32];
    snprintf(pos, sizeof pos, "%1.6f,%1.6f", lat, lon);
    drawCjkText((SW - cjkTextWidth(pos, 1)) / 2, 246, pos, C_YELLOW, 1);

    // 黄色操作条
    tft.fillRect(0, SH - 32, SW, 32, C_YELLOW);
    drawCjkText((SW - cjkTextWidth("返回详情", 1)) / 2, SH - 28, "返回详情", C_BLACK, 1);
}

static void render(void)
{
    switch (g_screen) {
    case SCR_HOME:   drawHome(); break;
    case SCR_LIST:   drawList(); break;
    case SCR_DETAIL: drawDetail(); break;
    case SCR_NAV:    drawNav(); break;
    case SCR_QR:     drawQr(); break;
    }
}

// ---------------- 按键事件 ----------------
static void handleEvent(BtnEvent ev)
{
    // 全局: B 键长按 = 屏幕亮灭切换(任意页面生效, 不影响其他按键语义)
    if (ev == EVT_B_LONG) {
        uiToggleBacklight();
        return;
    }
    int n = droneStoreActiveCount();
    switch (g_screen) {
    case SCR_HOME:
        if (ev == EVT_A_CLICK || ev == EVT_B_CLICK) {
            g_screen = SCR_LIST;
            g_listFocus = 0;
            g_listScroll = 0;
            g_dirty = true;
        }
        break;

    case SCR_LIST:
        if (ev == EVT_A_CLICK) {
            if (n > 0) {
                g_listFocus++;
                if (g_listFocus >= n) g_listFocus = 0;
                g_dirty = true;
            }
        } else if (ev == EVT_A_LONG) {
            if (n > 0 && g_listFocus < n) {
                g_detailIdx = g_listFocus;   // focus 即绝对索引(滚动后不可再加 scroll)
                g_navTarget = 0;
                g_screen = SCR_DETAIL;
                g_dirty = true;
            }
        } else if (ev == EVT_B_CLICK) {
            g_screen = SCR_HOME;
            g_dirty = true;
        }
        break;

    case SCR_DETAIL:
        if (ev == EVT_A_CLICK) {
            g_screen = SCR_NAV;         // 进入"选择导航目标"二级页
            g_dirty = true;
        } else if (ev == EVT_B_CLICK) {
            g_screen = SCR_LIST;
            g_dirty = true;
        }
        break;

    case SCR_NAV:
        if (ev == EVT_A_CLICK) {
            g_navTarget ^= 1;           // 切换 飞手↔飞机
            g_dirty = true;
        } else if (ev == EVT_A_LONG) {
            g_screen = SCR_QR;          // 确认并出码
            g_dirty = true;
        } else if (ev == EVT_B_CLICK) {
            g_screen = SCR_DETAIL;      // 返回详情
            g_dirty = true;
        }
        break;

    case SCR_QR:
        g_screen = SCR_DETAIL;
        g_dirty = true;
        break;
    }
}

// ---------------- 对外接口 ----------------
// 屏幕亮灭控制(B 键长按触发): 背光 GPIO38 + LCD 电源使能 GPIO15
static bool g_blOn = true;
void uiToggleBacklight(void)
{
    g_blOn = !g_blOn;
    digitalWrite(PIN_LCD_BL, g_blOn ? HIGH : LOW);
    digitalWrite(PIN_LCD_POWER, g_blOn ? HIGH : LOW);
    Serial.printf("[ui] 屏幕%s (B 长按可切换)\n", g_blOn ? "点亮" : "熄灭");
}

void uiInit(void)
{
    battInit();
    tft.setRotation(0);          // 170x320 竖屏(旋转 90°)
    tft.setTextFont(2);          // 8x16 ASCII
    tft.setTextSize(1);
    g_dirty = true;
}

void uiLoop(void)
{
    battUpdate();                       // 2s 更新一次本机电池电量
    BtnEvent ev;
    while ((ev = buttonsPoll()) != EVT_NONE) handleEvent(ev);
    // 数据为空时自动回主页
    if ((g_screen == SCR_LIST || g_screen == SCR_DETAIL ||
         g_screen == SCR_NAV || g_screen == SCR_QR) &&
        droneStoreActiveCount() == 0) {
        g_screen = SCR_HOME;
        g_dirty = true;
    }
    // DETAIL 索引越界保护
    if (g_screen == SCR_DETAIL && g_detailIdx >= droneStoreActiveCount()) {
        g_detailIdx = 0;
        g_dirty = true;
    }

    uint32_t now = millis();
    // 动态刷新策略:
    //  有无人机时 500ms 刷新一次(RSSI/位置实时更新);
    //  无无人机时不做周期整屏重绘, 仅信道变化/事件时刷新
    //   (整屏重绘电流脉冲大, 无数据时高频刷新会致供电弱时屏幕闪烁)
    static uint8_t s_lastCh = 0xFF;
    if (droneStoreActiveCount() > 0) {
        if (now - g_lastRefresh >= 500) {
            g_lastRefresh = now;
            g_dirty = true;
        }
    } else {
        uint8_t ch = snifferChannel();
        if (ch != s_lastCh) { s_lastCh = ch; g_dirty = true; }
    }
    if (g_dirty) {
        g_dirty = false;
        // 渲染期间暂停 WiFi 包处理, 防止高频中断打断 TFT 并行总线写入
        snifferPause();
        render();
        snifferResume();
    }
}

int uiBattPct(void)
{
    return s_battPct;
}
