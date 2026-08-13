#include <Arduino.h>
#include <TFT_eSPI.h>
#include "config.h"
#include "antenna.h"
#include "sniffer.h"
#include "drone_store.h"
#include "buttons.h"
#include "ui.h"

TFT_eSPI tft = TFT_eSPI();

// ============================================================
// LILYGO T-Display-S3 ST7789V 补充初始化序列(官方例程同款,
// 兼容新旧两版屏幕)
// ============================================================
typedef struct { uint8_t cmd; uint8_t data[14]; uint8_t len; } lcd_cmd_t;
static const lcd_cmd_t st7789v[] = {
    {0x11, {0}, 0 | 0x80},
    {0x3A, {0X05}, 1},
    {0xB2, {0X0B, 0X0B, 0X00, 0X33, 0X33}, 5},
    {0xB7, {0X75}, 1},
    {0xBB, {0X28}, 1},
    {0xC0, {0X2C}, 1},
    {0xC2, {0X01}, 1},
    {0xC3, {0X1F}, 1},
    {0xC6, {0X13}, 1},
    {0xD0, {0XA7}, 1},
    {0xD0, {0XA4, 0XA1}, 2},
    {0xD6, {0XA1}, 1},
    {0xE0, {0XF0, 0X05, 0X0A, 0X06, 0X06, 0X03, 0X2B, 0X32, 0X43, 0X36, 0X11, 0X10, 0X2B, 0X32}, 14},
    {0xE1, {0XF0, 0X08, 0X0C, 0X0B, 0X09, 0X24, 0X2B, 0X22, 0X43, 0X38, 0X15, 0X16, 0X2F, 0X37}, 14},
};

static void lcdCustomInit(void)
{
    for (unsigned i = 0; i < sizeof(st7789v) / sizeof(st7789v[0]); i++) {
        tft.writecommand(st7789v[i].cmd);
        for (int j = 0; j < (st7789v[i].len & 0x7f); j++)
            tft.writedata(st7789v[i].data[j]);
        if (st7789v[i].len & 0x80) delay(120);
    }
}

void setup(void)
{
    Serial.begin(115200);
    delay(200);

    // LCD 电源使能必须为高,否则 USB 未连接时屏幕不亮
    pinMode(PIN_LCD_POWER, OUTPUT);
    digitalWrite(PIN_LCD_POWER, HIGH);

    tft.init();
    tft.setRotation(0);   // 竖屏 170x320 (旋转 90°)
    tft.fillScreen(TFT_BLACK);
    // lcdCustomInit() 已移除: 自定义 ST7789V 寄存器序列(0xB2/0xBB/0xC0/0xD0/0xE0/0xE1 等)
    // 会覆盖 TFT_eSPI 标准初始化, 与部分屏幕批次不适配导致显示错乱(花屏/白块)。
    // 纯色测试固件已验证: 仅 tft.init() + setRotation(0) 即可正常驱动本屏。

    pinMode(PIN_LCD_BL, OUTPUT);
    digitalWrite(PIN_LCD_BL, HIGH);

    uiInit();
    droneStoreInit();
    buttonsInit();
    snifferInit();

    Serial.println(FW_NAME " " FW_VER " 启动完成 (纯接收模式)");
}

// ============================================================
// 串口 JSON 上报(供 PC 端监测大屏解析)
// 协议: 每秒一行全量快照
//   {"t":"snap","n":3,"ch":6,"bat":78,"drones":[
//     {"mac":"AA:BB:CC:00:11:22","model":"DJI Mavic 3","id":"1581F45QK9C2D12",
//      "rssi":-55,"lat":39.9112,"lon":116.4210,"alt":120.5,"spd":8.2,
//      "olat":39.9042,"olon":116.4074,"proto":0}, ... ]}
// 无坐标的字段缺省; PC 端容错解析。
// ============================================================
static uint32_t g_lastReport = 0;

static void serialReport(void)
{
    uint32_t now = millis();
    int n = droneStoreActiveCount();
    // 无无人机时降为 5s 心跳(PC 端维持连接即可):
    // USB CDC 高频打印的传输中断会与 TFT 并行总线写冲突(白块/闪烁),
    // 无数据时每秒打印空 JSON 纯属浪费
    if (n == 0) {
        if (now - g_lastReport < 5000) return;
    } else if (now - g_lastReport < 1000) {
        return;
    }
    g_lastReport = now;

    Serial.printf("{\"t\":\"snap\",\"n\":%d,\"ch\":%d,\"bat\":%d,\"drones\":[",
                  n, snifferChannel(), uiBattPct());
    for (int i = 0; i < n; i++) {
        const DroneEntry *d = droneStoreGet(i);
        if (!d) continue;
        if (i > 0) Serial.print(",");
        Serial.printf("{\"mac\":\"%02X:%02X:%02X:%02X:%02X:%02X\"",
                      d->mac[0], d->mac[1], d->mac[2], d->mac[3], d->mac[4], d->mac[5]);
        if (d->model[0]) Serial.printf(",\"model\":\"%s\"", d->model);
        if (d->uasId[0]) Serial.printf(",\"id\":\"%s\"", d->uasId);
        Serial.printf(",\"rssi\":%d", d->rssiLast);
        if (d->hasAircraftPos)
            Serial.printf(",\"lat\":%.6f,\"lon\":%.6f", d->aLat, d->aLon);
        if (d->altGeo > -999) Serial.printf(",\"alt\":%.1f", d->altGeo);
        if (d->hasSpeed) Serial.printf(",\"spd\":%.1f", d->speedH);
        if (d->hasOpPos)
            Serial.printf(",\"olat\":%.6f,\"olon\":%.6f", d->opLat, d->opLon);
        Serial.printf(",\"proto\":%d}", d->protocol);
    }
    Serial.println("]}");
}

void loop(void)
{
    snifferLoop();      // WiFi 信道轮询
    droneStoreTick();   // 无人机超时老化
    buttonsLoop();      // 按键扫描
    uiLoop();           // UI 刷新 + 事件
    serialReport();     // 串口 JSON 上报(1s)
    delay(2);
}
