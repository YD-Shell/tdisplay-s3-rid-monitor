#pragma once
#include <stdint.h>

// 按键事件
typedef enum {
    EVT_NONE = 0,
    EVT_A_CLICK,     // A 键短按(立即响应, 无双击判定延迟)
    EVT_A_LONG,      // A 键长按
    EVT_B_CLICK,     // B 键短按
    EVT_B_LONG,      // B 键长按(屏幕亮灭)
} BtnEvent;

void buttonsInit(void);
void buttonsLoop(void);      // 每 10ms 调用一次
BtnEvent buttonsPoll(void);  // 取走一个事件(无则 EVT_NONE)
