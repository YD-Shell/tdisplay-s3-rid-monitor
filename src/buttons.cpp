#include "buttons.h"
#include "config.h"
#include <Arduino.h>

#define BTN_DEBOUNCE_MS  20
#define BTN_LONG_MS      800
#define BTN_POLL_MS      10

// 按键状态机: 单击立即响应(无双击判定延迟, 避免快速连按误触)
//   A 单击=确认/切换   A 长按=进入详情/出码
//   B 单击=返回       B 长按=屏幕亮灭
typedef struct {
    int  pin;
    uint8_t state;       // 0=空闲 1=按下消抖 2=按住 3=松开消抖
    uint32_t tStamp;     // 状态跳变时间
    uint32_t tDown;      // 确认按下时间
    bool longFired;      // 已触发过长按
} Btn;

static Btn g_btnA = {PIN_BUTTON_A, 0, 0, 0, false};
static Btn g_btnB = {PIN_BUTTON_B, 0, 0, 0, false};

#define EVT_QUEUE 8
static BtnEvent g_queue[EVT_QUEUE];
static int g_qHead = 0, g_qTail = 0;

static void pushEvent(BtnEvent e)
{
    int next = (g_qTail + 1) % EVT_QUEUE;
    if (next == g_qHead) return;   // 满则丢弃
    g_queue[g_qTail] = e;
    g_qTail = next;
}

static void scanBtn(Btn *b, bool isA)
{
    bool pressed = (digitalRead(b->pin) == LOW);   // 按下=低
    uint32_t now = millis();
    switch (b->state) {
    case 0:
        if (pressed) { b->state = 1; b->tStamp = now; }
        break;
    case 1: // 消抖中
        if (!pressed) { b->state = 0; }
        else if (now - b->tStamp >= BTN_DEBOUNCE_MS) { b->state = 2; b->tDown = now; }
        break;
    case 2: // 按住
        if (!pressed) { b->state = 3; b->tStamp = now; }
        else if (!b->longFired && (now - b->tDown) >= BTN_LONG_MS) {
            b->longFired = true;
            if (isA) pushEvent(EVT_A_LONG);
            else     pushEvent(EVT_B_LONG);
        }
        break;
    case 3: // 松开消抖
        if (pressed) { b->state = 2; b->tDown = now; }
        else if (now - b->tStamp >= BTN_DEBOUNCE_MS) {
            b->state = 0;
            if (b->longFired) { b->longFired = false; break; }   // 长按后松开不再发单击
            if (isA) pushEvent(EVT_A_CLICK);
            else     pushEvent(EVT_B_CLICK);
        }
        break;
    }
}

void buttonsInit(void)
{
    pinMode(PIN_BUTTON_A, INPUT_PULLUP);
    if (PIN_BUTTON_B >= 0) pinMode(PIN_BUTTON_B, INPUT_PULLUP);
}

void buttonsLoop(void)
{
    static uint32_t last = 0;
    uint32_t now = millis();
    if (now - last < BTN_POLL_MS) return;
    last = now;

    scanBtn(&g_btnA, true);
    if (PIN_BUTTON_B >= 0) scanBtn(&g_btnB, false);
}

BtnEvent buttonsPoll(void)
{
    if (g_qHead == g_qTail) return EVT_NONE;
    BtnEvent e = g_queue[g_qHead];
    g_qHead = (g_qHead + 1) % EVT_QUEUE;
    return e;
}
