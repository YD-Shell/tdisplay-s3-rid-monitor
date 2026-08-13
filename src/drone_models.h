#pragma once
// ============================================================
// 无人机识别: 具体型号 + 品牌
// ------------------------------------------------------------
// 1) 具体型号: DJI 无人机在 ASTM F3411 / CN 46750-2025 RID 消息中
//    广播机身序列号(SN),SN 前 8 位为机型代码,按"前缀最长优先"
//    匹配后显示如 "DJI Mini 5 Pro"。数据为社区采集(2021-2026 机型),
//    未收录/新增机型请直接在下表追加(prefix 越具体越长越优先)。
//
// 2) 品牌兜底: 其他厂商(道通/Parrot/飞米/哈博森...)暂无可用的
//    公开 SN→型号表,改用发射 MAC 的 IEEE OUI 注册前缀识别品牌,
//    显示如 "道通无人机" / "Parrot无人机"。数据来自 IEEE 官方
//    MA-L/MA-M/MA-S 注册表(maclookup.app 免费库, 2026-08)。
//
// 优先级: 具体型号 > 品牌 > 协议分类标签(UAType)。
// ============================================================
#include <string.h>
#include <ctype.h>
#include <stdio.h>

// ---------------- 1. DJI 具体型号表(SN 前缀) ----------------
typedef struct {
    const char *prefix;   // SN 前缀(大写)
    const char *name;     // 具体型号(不含 "DJI " 前缀)
} DJI_Model;

static const DJI_Model DJI_MODELS[] = {
    /* --- 消费级 --- */
    {"1581F8LQ", "Mavic 4 Pro"},
    {"1581F67Q", "Mavic 3 Pro"},
    {"1581F5Y8", "Mavic 3 Classic"},
    {"1581F45Q", "Mavic 3"},
    {"1581F895", "Air 3S"},
    {"1581F6N8", "Air 3"},
    {"1581F385", "Air 2S"},
    {"1581FANL", "Mini 5 Pro"},
    {"1581F9DE", "Mini 5 Pro"},
    {"1581F5QJ", "Mini 4 Pro"},
    {"1581F8C8", "Mini 4K"},
    {"1581F4XF", "Mini 3 Pro"},
    {"1581F6CD", "Mini 2 SE"},
    {"1581FA8J", "Avata 360"},
    {"1581FBV5", "Lito 1"},
    {"1581FB34", "Lito X1"},
    /* --- 穿越机 --- */
    {"1581F6W8", "Avata 2"},
    {"1581F4CQ", "Avata"},
    {"1581FA6Q", "Neo 2"},
    {"1581F8A1", "Neo"},
    {"1581F3CQ", "FPV"},
    {"1581F7V2", "Flip"},
    /* --- 行业级 --- */
    {"1581F6H8", "Matrice 350 RTK"},
    {"1581F5BK", "Matrice 30"},
    {"1581F52Q", "Mavic 3E/3T"},
    {"1581F578", "Inspire 3"},
};

#define DJI_MODEL_COUNT (sizeof(DJI_MODELS) / sizeof(DJI_MODELS[0]))

// ---------------- 2. 品牌表(MAC OUI 前缀) ----------------
// b3 = 0xFF: 仅匹配前 3 字节(MA-L)
// b3 < 16 : 匹配前 3 字节 + MAC[3] 高 4 位 == b3 (MA-M/MA-S)
typedef struct {
    uint8_t b0, b1, b2, b3;
    const char *brand;
} OUI_Brand;

static const OUI_Brand OUI_BRANDS[] = {
    /* --- 大疆 DJI(SN 识别不到的兜底) --- */
    {0x60, 0x60, 0x1F, 0xFF, "大疆"},
    {0x34, 0xD2, 0x62, 0xFF, "大疆"},
    {0xE4, 0x7A, 0x2C, 0xFF, "大疆"},
    {0x58, 0xB8, 0x58, 0xFF, "大疆"},
    {0x04, 0xA8, 0x5A, 0xFF, "大疆"},
    {0x8C, 0x58, 0x23, 0xFF, "大疆"},
    {0x0C, 0x9A, 0xE6, 0xFF, "大疆"},
    {0x88, 0x29, 0x85, 0xFF, "大疆"},
    {0x4C, 0x43, 0xF6, 0xFF, "大疆"},
    {0x9C, 0x5A, 0x8A, 0xFF, "大疆"},   // DJI Baiwang
    {0xEC, 0x72, 0xF7, 0xFF, "大疆"},
    {0x34, 0x91, 0xF0, 0xFF, "大疆"},
    /* --- 道通 Autel --- */
    {0x18, 0xD7, 0x93, 0x6,  "道通"},   // Autel Intelligent Technology (深圳道通智能)
    {0xEC, 0x5B, 0xCD, 0xE,  "道通"},   // Autel Robotics USA LLC
    /* --- 其他品牌 --- */
    {0x00, 0x26, 0x7E, 0xFF, "Parrot"},
    {0x00, 0x12, 0x1C, 0xFF, "Parrot"},
    {0x90, 0x03, 0xB7, 0xFF, "Parrot"},
    {0xA0, 0x14, 0x3D, 0xFF, "Parrot"},
    {0x90, 0x3A, 0xE6, 0xFF, "Parrot"},
    {0x38, 0x1D, 0x14, 0xFF, "Skydio"},
    {0x6C, 0xDF, 0xFB, 0xE,  "飞米"},   // FIMI (小米生态)
    {0x98, 0xAA, 0xFC, 0x7,  "哈博森"}, // Hubsan
    {0xE0, 0xB6, 0xF5, 0x8,  "昊翔"},   // Yuneec
    {0xA4, 0x51, 0x29, 0xFF, "极飞"},   // XAG (农业无人机)
    {0x54, 0x7D, 0x40, 0xFF, "臻迪"},   // PowerVision
    {0x00, 0x1C, 0x0A, 0xFF, "一电"},   // AEE
    {0xB0, 0x30, 0xC8, 0xFF, "Teal"},
    {0x00, 0x0C, 0xBF, 0xFF, "Holy Stone"},
    {0xD4, 0xA0, 0xFB, 0xB,  "Hover"},  // Spatial Hover (ZeroZero)
    {0x24, 0xA1, 0x0D, 0x7,  "Cyon"},
};

#define OUI_BRAND_COUNT (sizeof(OUI_BRANDS) / sizeof(OUI_BRANDS[0]))

// ---------------- 查询函数 ----------------
// SN 前缀匹配(忽略大小写), 返回命中的型号名; 未命中返回 NULL
static inline const char *djiModelLookup(const char *id)
{
    if (!id || !id[0]) return NULL;
    size_t best = 0;
    const char *found = NULL;
    for (size_t i = 0; i < DJI_MODEL_COUNT; i++) {
        const char *p = DJI_MODELS[i].prefix;
        size_t pl = strlen(p);
        if (pl > best && strncasecmp(id, p, pl) == 0) {
            best = pl;
            found = DJI_MODELS[i].name;
        }
    }
    return found;
}

// MAC OUI 品牌匹配, 返回品牌名; 未命中返回 NULL
static inline const char *ouiBrandLookup(const uint8_t *mac)
{
    if (!mac) return NULL;
    for (size_t i = 0; i < OUI_BRAND_COUNT; i++) {
        const OUI_Brand *b = &OUI_BRANDS[i];
        if (mac[0] == b->b0 && mac[1] == b->b1 && mac[2] == b->b2 &&
            (b->b3 == 0xFF || (mac[3] >> 4) == b->b3))
            return b->brand;
    }
    return NULL;
}

// 生成完整显示名 "DJI <型号>" (型号已含 DJI 则不重复), 写入 buf
static inline void djiModelDisplay(const char *id, char *buf, size_t len)
{
    buf[0] = 0;
    const char *m = djiModelLookup(id);
    if (!m) return;
    if (strncasecmp(m, "DJI", 3) == 0)
        snprintf(buf, len, "%s", m);
    else
        snprintf(buf, len, "DJI %s", m);
}

// 生成品牌显示名 "<品牌>无人机", 写入 buf
static inline void ouiBrandDisplay(const uint8_t *mac, char *buf, size_t len)
{
    buf[0] = 0;
    const char *b = ouiBrandLookup(mac);
    if (!b) return;
    snprintf(buf, len, "%s无人机", b);
}
