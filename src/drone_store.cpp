#include "drone_store.h"
#include "config.h"
#include "drone_models.h"
#include <Arduino.h>
#include <string.h>

static DroneEntry g_drones[MAX_DRONES];
static int g_order[MAX_DRONES];   // 有效条目按 rssiBest 降序的索引
static int g_count = 0;

static DroneEntry *findByMac(const uint8_t *mac)
{
    for (int i = 0; i < MAX_DRONES; i++)
        if (g_drones[i].active && memcmp(g_drones[i].mac, mac, 6) == 0)
            return &g_drones[i];
    return NULL;
}

static DroneEntry *findByUasId(const char *id)
{
    if (!id || !id[0]) return NULL;
    for (int i = 0; i < MAX_DRONES; i++)
        if (g_drones[i].active && strcmp(g_drones[i].uasId, id) == 0)
            return &g_drones[i];
    return NULL;
}

static DroneEntry *allocSlot(void)
{
    // 优先复用失效槽位
    for (int i = 0; i < MAX_DRONES; i++)
        if (!g_drones[i].active) {
            memset(&g_drones[i], 0, sizeof(DroneEntry));
            g_drones[i].rssiBest = 0;
            g_drones[i].rssiLast = 0;
            g_drones[i].battery = -1;
            g_drones[i].altGeo = -1000;
            g_drones[i].altRel = -1000;
            g_drones[i].active = true;
            return &g_drones[i];
        }
    // 全满:顶掉最弱信号
    int worst = -1;
    for (int i = 0; i < MAX_DRONES; i++)
        if (worst < 0 || g_drones[i].rssiBest < g_drones[worst].rssiBest)
            worst = i;
    if (worst >= 0) {
        memset(&g_drones[worst], 0, sizeof(DroneEntry));
        g_drones[worst].rssiBest = 0;
        g_drones[worst].rssiLast = 0;
        g_drones[worst].battery = -1;
        g_drones[worst].altGeo = -1000;
        g_drones[worst].altRel = -1000;
        g_drones[worst].active = true;
        return &g_drones[worst];
    }
    return NULL;
}

static void refreshOrder(void)
{
    g_count = 0;
    for (int i = 0; i < MAX_DRONES; i++)
        if (g_drones[i].active) g_order[g_count++] = i;
    // 冒泡:按 rssiBest 降序
    for (int i = 0; i < g_count - 1; i++)
        for (int j = 0; j < g_count - 1 - i; j++)
            if (g_drones[g_order[j]].rssiBest < g_drones[g_order[j + 1]].rssiBest) {
                int t = g_order[j]; g_order[j] = g_order[j + 1]; g_order[j + 1] = t;
            }
}

void droneStoreInit(void)
{
    memset(g_drones, 0, sizeof(g_drones));
    for (int i = 0; i < MAX_DRONES; i++) {
        g_drones[i].battery = -1;
        g_drones[i].altGeo = -1000;
        g_drones[i].altRel = -1000;
    }
    refreshOrder();
}

// 机型/品牌识别: 优先 DJI SN→具体型号, 兜底 MAC OUI→品牌
static void resolveModel(DroneEntry *d)
{
    djiModelDisplay(d->uasId, d->model, sizeof d->model);
    if (!d->model[0]) ouiBrandDisplay(d->mac, d->model, sizeof d->model);
}

void droneStoreIngest(const ODID_UAS_Data *uas, const uint8_t *mac, int rssi, int proto)
{
    DroneEntry *d = NULL;
    // 优先按 UAS ID 匹配
    if (uas->BasicIDValid[0] && uas->BasicID[0].UASID[0])
        d = findByUasId(uas->BasicID[0].UASID);
    if (!d) d = findByMac(mac);
    if (!d) d = allocSlot();
    if (!d) return;

    d->active = true;
    d->lastSeen = millis();
    memcpy(d->mac, mac, 6);
    d->protocol = (uint8_t)proto;   // 0=ASTM WiFi 1=CN WiFi 2=BLE
    d->packets++;
    d->rssiLast = (int8_t)rssi;
    if (rssi > d->rssiBest) d->rssiBest = (int8_t)rssi;

    if (uas->BasicIDValid[0]) {
        strncpy(d->uasId, uas->BasicID[0].UASID, 20);
        d->uasId[20] = 0;
        d->idType = uas->BasicID[0].IDType;
        d->uaType = uas->BasicID[0].UAType;
        resolveModel(d);
    }
    if (uas->LocationValid) {
        if (uas->Location.Latitude != 0 || uas->Location.Longitude != 0) {
            d->aLat = uas->Location.Latitude;
            d->aLon = uas->Location.Longitude;
            d->hasAircraftPos = true;
        }
        if (uas->Location.AltitudeGeo > -999.0f) d->altGeo = uas->Location.AltitudeGeo;
        if (uas->Location.Height > -999.0f)      d->altRel = uas->Location.Height;
        if (uas->Location.SpeedHorizontal < 254.0f) {
            d->speedH = uas->Location.SpeedHorizontal;
            d->hasSpeed = true;
        }
        d->speedV = uas->Location.SpeedVertical;
        d->status = uas->Location.Status;
    }
    if (uas->SystemValid &&
        (uas->System.OperatorLatitude != 0 || uas->System.OperatorLongitude != 0)) {
        d->opLat = uas->System.OperatorLatitude;
        d->opLon = uas->System.OperatorLongitude;
        d->hasOpPos = true;
    }
    if (uas->OperatorIDValid) {
        strncpy(d->opId, uas->OperatorID.OperatorId, 20);
        d->opId[20] = 0;
    }
    if (uas->SelfIDValid) {
        strncpy(d->selfDesc, uas->SelfID.Desc, 23);
        d->selfDesc[23] = 0;
    }
    refreshOrder();
}

void droneStoreIngestCN(const DroneRIDData_t *cn, const uint8_t *mac, int rssi)
{
    DroneEntry *d = findByMac(mac);
    if (!d) d = findByUasId(cn->sn);
    if (!d) d = allocSlot();
    if (!d) return;

    d->active = true;
    d->lastSeen = millis();
    memcpy(d->mac, mac, 6);
    d->protocol = 1;
    d->packets++;
    d->rssiLast = (int8_t)rssi;
    if (rssi > d->rssiBest) d->rssiBest = (int8_t)rssi;

    strncpy(d->uasId, cn->sn, 20);
    d->uasId[20] = 0;
    d->uaType = (uint8_t)(100 + cn->drone_class);   // 100+ 表示 CN 分类
    d->idType = 1;  // 序列号
    resolveModel(d);

    if (cn->drone_lat != 0 || cn->drone_lon != 0) {
        d->aLat = cn->drone_lat;
        d->aLon = cn->drone_lon;
        d->hasAircraftPos = true;
    }
    d->altGeo = cn->drone_alt;
    if (cn->has_rel_alt) d->altRel = cn->rel_alt;
    d->speedH = cn->ground_speed;
    d->speedV = cn->has_v_speed ? cn->vertical_speed : 0;
    d->hasSpeed = true;
    d->status = cn->op_status;

    d->opLat = cn->gcs_lat;
    d->opLon = cn->gcs_lon;
    d->hasOpPos = true;
    // CN 实名登记后 8 位 → 显示为注册号
    strncpy(d->opId, cn->uin, 8);
    d->opId[8] = 0;

    refreshOrder();
}

void droneStoreTick(void)
{
    uint32_t now = millis();
    bool changed = false;
    for (int i = 0; i < MAX_DRONES; i++) {
        if (g_drones[i].active && (now - g_drones[i].lastSeen) > DRONE_TIMEOUT_MS) {
            g_drones[i].active = false;
            changed = true;
        }
    }
    if (changed) refreshOrder();
}

int droneStoreCount(void)      { return g_count; }
int droneStoreActiveCount(void)
{
    int n = 0;
    for (int i = 0; i < MAX_DRONES; i++) if (g_drones[i].active) n++;
    return n;
}
const DroneEntry *droneStoreGet(int idx)
{
    if (idx < 0 || idx >= g_count) return NULL;
    return &g_drones[g_order[idx]];
}
