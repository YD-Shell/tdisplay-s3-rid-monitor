#pragma once
#include <stdint.h>
#include <TFT_eSPI.h>

extern TFT_eSPI tft;
void uiInit(void);
void uiLoop(void);   // 处理按键事件 + 周期刷新
int  uiBattPct(void); // 本机电量百分比; -1 = USB 供电(未接电池)
void uiToggleBacklight(void); // 切换屏幕亮灭(B 键长按)
