#include "antenna.h"
#include "config.h"
#include <Arduino.h>
#include <esp_wifi.h>

// 强制固定使用外部天线,关闭板载 PCB 天线。
// 关键点:使用 WIFI_ANT_MODE_ANT0/ANT1(即 FIXED 固定模式),
//         绝不使用 WIFI_ANT_MODE_AUTO —— 自动模式会在内外天线间
//         来回切换,导致弱信号断断续续。
//
// 硬件注意:ESP32-S3-WROOM-1 模块本身没有 RF 切换开关
//   (WROOM-1 = 板载 PCB 天线固定; -1U = 外置天线固定),
//   因此对标准 T-Display-S3 而言,本函数的效果等价于
//   "固定天线、永不自动切换"; 若你的板子带天线切换 GPIO,
//   配置 config.h 中的 ANT_SEL_GPIO0/1 与 EXTERNAL_ANT_INDEX 即可。
void antennaForceExternal(void)
{
#if FORCE_EXTERNAL_ANTENNA
    // 1) 配置射频开关 GPIO(对带切换开关的模块/板子生效)
    wifi_ant_gpio_config_t antGpio = {0};
    antGpio.gpio_cfg[0].gpio_select = 1;
    antGpio.gpio_cfg[0].gpio_num   = ANT_SEL_GPIO0;
    antGpio.gpio_cfg[1].gpio_select = 1;
    antGpio.gpio_cfg[1].gpio_num   = ANT_SEL_GPIO1;
    esp_err_t e1 = esp_wifi_set_ant_gpio(&antGpio);

    // 2) 强制固定使用外部天线(本固件只收不发)
    wifi_ant_config_t antCfg;
    memset(&antCfg, 0, sizeof(antCfg));
    antCfg.rx_ant_mode  = (wifi_ant_mode_t)(EXTERNAL_ANT_INDEX ? WIFI_ANT_MODE_ANT1 : WIFI_ANT_MODE_ANT0);
    antCfg.rx_ant_default = (wifi_ant_t)EXTERNAL_ANT_INDEX;
    antCfg.tx_ant_mode  = (wifi_ant_mode_t)(EXTERNAL_ANT_INDEX ? WIFI_ANT_MODE_ANT1 : WIFI_ANT_MODE_ANT0);
    esp_err_t e2 = esp_wifi_set_ant(&antCfg);

    Serial.printf("[antenna] gpio=%d/%d ant=ANT%d set_ant_gpio=%d set_ant=%d\n",
                  ANT_SEL_GPIO0, ANT_SEL_GPIO1, EXTERNAL_ANT_INDEX, e1, e2);
#else
    Serial.println("[antenna] FORCE_EXTERNAL_ANTENNA=0, 未强制天线");
#endif
}
