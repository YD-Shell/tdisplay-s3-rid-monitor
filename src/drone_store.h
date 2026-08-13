#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "odid/opendroneid.h"
#include "odidcn/opendroneidcn.h"

// 无人机条目(归一化模型,同时支持 ASTM F3411 与国标 CN 46750-2025)
typedef struct {
    bool active;            // 是否在跟踪(超时自动失效)
    uint32_t lastSeen;      // 最后收到数据的时间 (ms)
    uint8_t mac[6];         // 发射方 MAC (BSSID/SA)
    int8_t  rssiLast;       // 最近一次信号强度 (dBm)
    int8_t  rssiBest;       // 最强信号 (dBm)
    uint32_t packets;       // 收到包计数
    uint8_t protocol;       // 0=ASTM F3411  1=CN 46750-2025

    // 身份
    char   uasId[21];       // 序列号 / 产品识别码
    char   model[24];       // 识别的具体机型显示名,如 "DJI Mini 5 Pro"; 空=未知
    uint8_t idType;         // ASTM IDType: 1=序列号 2=注册号 3=UTM 4=会话
    uint8_t uaType;         // ASTM UAType; 100+ = CN 无人机分类
    // 飞机状态
    bool   hasAircraftPos;
    double aLat, aLon;      // 飞机经纬度
    float  altGeo;          // 海拔 (m, WGS84), -1000 = 未知
    float  altRel;          // 相对高度 (m), -1000 = 未知
    bool   hasSpeed;
    float  speedH;          // 水平速度 (m/s)
    float  speedV;          // 垂直速度 (m/s)
    uint8_t status;         // 0未声明 1地面 2空中 3紧急 4故障
    // 飞手(操作员)
    bool   hasOpPos;
    double opLat, opLon;    // 飞手经纬度
    char   opId[21];        // 操作员注册号 (ASTM OperatorID / CN 实名登记)
    char   selfDesc[24];    // 自描述文本 (ASTM SelfID)
    // 电量:标准协议(ASTM F3411 / CN 46750)均无电量字段,
    // -1 = 未知; 预留厂商扩展解析 hook, 解析到后回填此处
    int8_t battery;
} DroneEntry;

void droneStoreInit(void);

// 输入一条解码后的 ASTM ODID 数据(可能只含部分消息,内部做增量合并)
// 标准协议(ASTM F3411 / CN 46750)数据入库; proto: 0=ASTM WiFi 1=CN WiFi 2=BLE
void droneStoreIngest(const ODID_UAS_Data *uas, const uint8_t *mac, int rssi, int proto);
// 输入一条解码后的国标 CN 46750-2025 数据
void droneStoreIngestCN(const DroneRIDData_t *cn, const uint8_t *mac, int rssi);

// 每帧调用:超时老化
void droneStoreTick(void);

// 当前跟踪(含已超时但未清空)数量
int droneStoreCount(void);
// 有效(未超时)数量
int droneStoreActiveCount(void);
// 按信号强度降序取第 idx 个有效条目
const DroneEntry *droneStoreGet(int idx);
