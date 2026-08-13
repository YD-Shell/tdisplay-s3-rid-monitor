#include "sniffer.h"
#include "config.h"
#include "antenna.h"
#include "drone_store.h"
#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>

// ============================================================
// WiFi 嗅探:仅接收(promiscuous RX),不连接、不发射任何数据。
// 发射会抬高本机底噪,把微弱的 RID 信号淹没,因此本固件
// 绝不调用 WiFi.begin() / AP / 任何发送接口。
// ============================================================

static const uint8_t g_channels[] = RID_CHANNELS;
static const int g_channelCount = (int)(sizeof(g_channels) / sizeof(g_channels[0]));
static int g_channelIdx = 0;
static uint32_t g_lastHop = 0;

uint8_t snifferChannel(void) { return g_channels[g_channelIdx]; }

// 尝试解码一段 ODID 载荷(兼容 [计数器+消息包] 与 [消息包/单消息] 两种布局)
static bool tryDecode(ODID_UAS_Data *uas, const uint8_t *buf, int len)
{
    if (!buf || len < 1) return false;
    ODID_messagetype_t r = decodeOpenDroneID(uas, buf);
    return (r != ODID_MESSAGETYPE_INVALID);
}

// 处理一个 ODID 厂商 IE 载荷(已越过 OUI, 指向 [type][...])
static void handleOdidPayload(const uint8_t *d, int len, const uint8_t *mac, int rssi)
{
    ODID_UAS_Data uas;
    odid_initUasData(&uas);

    // 标准 F3411-22 布局: [counter][pack|single] → 先跳过计数器(偏移 1)
    bool ok = false;
    if (len >= 2 && tryDecode(&uas, d + 1, len - 1)) ok = true;
    // 兼容无计数器的旧式布局
    if (!ok && len >= 1 && tryDecode(&uas, d, len)) ok = true;

    if (ok) droneStoreIngest(&uas, mac, rssi, 0);   // 0=ASTM WiFi
}

static void handleBeaconOrProbe(const uint8_t *p, uint16_t pktLen, int rssi)
{
    if (pktLen < 24 + 12) return;
    const uint8_t *mac = p + 10;            // addr2 = 发射方 MAC
    const uint8_t *body = p + 24;           // 802.11 头之后
    const uint8_t *end  = p + pktLen;

    // 1) 遍历 Tagged Parameters,找 ODID 厂商 IE
    const uint8_t *t = body + 12;           // 跳过 beacon 固定字段
    while (t + 2 <= end) {
        uint8_t id = t[0], len = t[1];
        if (t + 2 + len > end) break;
        if (id == 0xDD && len >= 4) {
            const uint8_t *d = t + 2;
            // OUI: FA:0B:BC (ASD-STAN / F3411-22) 或 FA:0B:57 (旧 ASTM)
            // type: 0x0D (Open Drone ID), 0x0E (旧式消息包)
            if (d[0] == 0xFA && d[1] == 0x0B && (d[2] == 0xBC || d[2] == 0x57) &&
                (d[3] == 0x0D || d[3] == 0x0E)) {
                handleOdidPayload(d + 4, (int)len - 4, mac, rssi);
            }
        }
        t += 2 + len;
    }

    // 2) 国标 CN 46750-2025:在 beacon body 中定位数据包
    size_t off = 0, ridLen = 0;
    if (CN46750_FindPacket(body, (size_t)(end - body), &off, &ridLen)) {
        DroneRIDData_t cn;
        if (CN46750_RID_Decode(body + off, ridLen, &cn, NULL) == RID_OK)
            droneStoreIngestCN(&cn, mac, rssi);
    }
}

// promiscuous 回调
static void snifferCb(void *buf, wifi_promiscuous_pkt_type_t type)
{
    if (type != WIFI_PKT_MGMT) return;
    wifi_promiscuous_pkt_t *pkt = (wifi_promiscuous_pkt_t *)buf;
    if (!pkt) return;
    uint16_t pktLen = pkt->rx_ctrl.sig_len;   // 帧长度
    if (pktLen < 24) return;

    const uint8_t *p = pkt->payload;
    uint8_t fc0 = p[0];
    uint8_t ftype   = (fc0 >> 2) & 0x03;    // 0=管理帧
    uint8_t subtype = (fc0 >> 4) & 0x0F;
    if (ftype != 0) return;

    int rssi = pkt->rx_ctrl.rssi;
    if (rssi < RSSI_FILTER_DBM) return;     // RSSI 过滤阈值

    if (subtype == 8 || subtype == 5) {     // Beacon / Probe Response
        handleBeaconOrProbe(p, pktLen, rssi);
    } else if (subtype == 13) {             // Action (NAN)
        ODID_UAS_Data uas;
        odid_initUasData(&uas);
        char mac[6];
        if (odid_wifi_receive_message_pack_nan_action_frame(&uas, mac, p, pktLen) == 0)
            droneStoreIngest(&uas, (const uint8_t *)mac, rssi, 0);   // Action 帧 = ASTM WiFi
    }
}

void snifferInit(void)
{
    // 仅初始化 STA 模式 + promiscuous 接收;绝不连接、绝不发送
    WiFi.mode(WIFI_STA);
    delay(50);
    antennaForceExternal();                 // 强制外部天线(FIXED, 非 AUTO)
    esp_wifi_set_ps(WIFI_PS_NONE);          // 关闭省电,保持常收
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_promiscuous_rx_cb(snifferCb);
    esp_wifi_set_channel(g_channels[0], WIFI_SECOND_CHAN_NONE);
    g_lastHop = millis();
    Serial.printf("[sniffer] 监听信道: 1/%d/%d, RSSI 阈值: %d dBm, 纯接收模式\n",
                  g_channels[0], g_channels[1], (int)RSSI_FILTER_DBM);
}

// 渲染期间暂停包处理(回调置空): 避免高频中断打断 TFT 并行总线写入
void snifferPause(void)
{
    esp_wifi_set_promiscuous_rx_cb(NULL);
}
void snifferResume(void)
{
    esp_wifi_set_promiscuous_rx_cb(snifferCb);
}

void snifferLoop(void)
{
    uint32_t now = millis();
    if (now - g_lastHop >= CHANNEL_DWELL_MS) {
        g_lastHop = now;
        g_channelIdx = (g_channelIdx + 1) % g_channelCount;
        esp_wifi_set_channel(g_channels[g_channelIdx], WIFI_SECOND_CHAN_NONE);
    }
}
