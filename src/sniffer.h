#pragma once
#include <stdint.h>
// WiFi 纯接收嗅探:只收不发,解析 ASTM F3411 ODID 与国标 CN 46750-2025
void snifferInit(void);
void snifferLoop(void);        // 信道轮询
uint8_t snifferChannel(void);  // 当前信道

// 渲染期间暂停/恢复 WiFi 包处理:
// TFT 并行总线(GPIO39-48)与 WiFi 接收回调共用 CPU, 渲染时若不暂停,
// 高频中断会打断屏幕写入导致局部像素错乱(白块/闪烁)。
void snifferPause(void);
void snifferResume(void);
