# T-Display-S3 无人机 RID 监测固件 v1.0

基于 **LILYGO T-Display-S3**(ESP32-S3, 1.9" 屏,**竖屏 170×320,rotation 0**)的**被动式 Remote ID(远程识别)监测器**。
纯接收侦听,不发射任何 WiFi 数据,可发现并解析附近无人机广播的 ASTM F3411 / 国标 CN 46750-2025 识别信息,
在屏幕上显示机型、序列号、飞手/飞机经纬度、信号强度、BSSID、高度、速度,并支持一键生成**飞手/飞机位置导航二维码**。

---

## 一、功能清单(对照需求)

> **UI v4 深蓝科技风**(170×320 竖屏)：渐变标题栏+高光底边 / 主页状态卡
> (大号 CH 信道 + 无人机计数 + 侦测状态点) / 卡片式列表行(序号徽章+高光线)
> / 详情页分组信息流(标识·位置·监测) / 暗红渐变机型横幅 / 导航页图标选项卡。
> 模拟器已同步: `simulation/simulator.html` 双击即看全部页面。

| 需求 | 实现 |
|------|------|
| 强制外部天线,关闭板载 PCB 天线,不要 Auto | 天线强制 **FIXED 固定模式**(`WIFI_ANT_MODE_ANT0/ANT1`),绝不使用 `AUTO` 自动切换(自动模式内外天线来回切换会导致信号断续)。见 `src/antenna.cpp` 与"硬件注意"章节 |
| 不开任何 WiFi 发射,只收不发 | 全程 `promiscuous` 纯接收,不调用 `WiFi.begin()`/AP/任何发送接口;关闭 WiFi 省电(`WIFI_PS_NONE`)保证连续侦听 |
| RSSI 过滤阈值 90dBm | `RSSI_FILTER_DBM = -90`,低于 -90dBm 的包直接丢弃(`config.h` 可改) |
| 一键导航到飞手/飞机二维码 | 详情页→"选择导航目标"二级页(飞手/飞机大选项+位置预览)→长按生成位置二维码,默认高德地图链接(手机扫码即导航),支持 Google/geo 切换 |
| 识别机型和 SN 码 | 机型(ASTM UAType 中文标签 / 国标无人机分类);**DJI 设备自动识别具体型号**(如 "DJI Mini 5 Pro"、"DJI Mavic 3",按序列号前缀匹配);**其他品牌按 MAC OUI 识别到品牌级**(道通/Parrot/Skydio/飞米/哈博森/昊翔/极飞等,显示"道通无人机"),识别表见 `src/drone_models.h`,可自行扩充 |
| 飞手经纬度 / 飞机经纬度 | 飞机位置来自 Location 消息;飞手位置来自 System 消息(操作员位置)或国标 GCS 位置 |
| 信号强度数值 + 标准柱状信号图 | 每架无人机行尾与详情页头部均显示 `-XXdBm` 数值 + 4 格标准信号柱 |
| BSSID / 高度 / 速度 | 详情页完整显示:BSSID(发射 MAC)、海拔、相对高度、水平速度(km/h) |
| 机身电量显示(监测设备自身) | 主页状态栏:**电池图标 + 百分比**(电量>50%绿、>20%黄、低电红);详情页:**本机电量:XX%**(IO4 ADC 检测,1/2 分压;未接电池时显示 USB)。被监测无人机的电量:标准 RID 协议无此字段,无法被动获取(见五.2) |
| 主页显示"已发现无人机" | 主页横幅:绿色"已发现无人机 N 架"/灰色"未发现无人机" |
| 按键进入二级菜单选择无人机 → 选择飞手/飞机 → 显示位置二维码 | 完整按键状态机:主页→列表(二级菜单)→详情→二维码,见"操作说明" |

额外支持:**国标 CN 46750-2025**(2026-05-01 起施行的《民用无人驾驶航空器系统运营识别规范》)解析,
以及 WiFi NAN(action 帧)方式的 RID 广播。

---

## 二、操作说明(按键)

| 按键 | 短按(单击) | 长按(0.8s) |
|------|------------|-------------|
| **A 键**(IO0 / BOOT) | 主页→进入列表;列表→下移焦点;详情→进入"选择导航目标"页;导航页→切换目标(飞手↔飞机) | 列表→打开选中无人机详情;导航页→确认并出码 |
| **B 键**(IO14) | 返回上一页(主页时进入列表) | **屏幕亮灭切换**(任意页面生效;背光 GPIO38 + LCD 电源 GPIO15 一并关断, 侦听不受影响) |

> 单击**立即响应**(无双击判定延迟, 避免快速连按误触)。

页面流转:
```
主页(发现横幅+列表)  --A短按-->  二级菜单(选择无人机)  --A长按-->  详情
                                                                    │
详情(竖向信息流)  --A短按-->  选择导航目标(飞手/飞机)  --A长按-->  二维码(手机扫码导航)
                    │                                              │
                    └--A短按 切换目标--┘           --任意键-->  返回详情
```

---

## 三、编译与烧录

### 环境
- 安装 [VS Code + PlatformIO](https://platformio.org/install/ide?install=ide) 或命令行 PlatformIO
- 本项目基于 `platform = espressif32@6.9.0`(Arduino core 2.0.x / IDF 4.4)

### 编译
```bash
pio run
```
首次运行会自动下载 ESP32 平台与工具链(约 500MB),之后很快。

### 烧录
```bash
pio run -t upload
```
- T-Display-S3 使用 **USB-C 原生 USB**,首次烧录若失败,请**按住 BOOT 键再插 USB**,松开后重新 `pio run -t upload`。
- 串口监视:`pio device monitor`(115200)。

### 产物
固件位于 `.pio/build/tdisplay-s3/firmware.bin`(app-only,烧 0x10000);项目根目录另有
**合并完整镜像 `tdisplay-s3-rid-monitor-v1.0-full.bin`**(bootloader+分区表+app,烧 0x0 即可):

```bash
esptool.py --chip esp32s3 --port COM5 --baud 921600 write_flash -z 0x0 tdisplay-s3-rid-monitor-v1.0-full.bin
```

### 串口数据上报
固件每秒向串口(115200)输出一行 JSON 快照(见 `src/main.cpp` 的 `serialReport()`),
供 PC 端智慧大屏解析——**该功能为新增,旧固件无此输出**,烧录新固件后生效。

---

## 三·五、智慧大屏(PC 端监测)

固件通过 USB 串口连电脑后,可在浏览器打开**高德地图智慧大屏**:
中央地图实时标绘无人机/飞手位置,左侧无人机列表(型号/信号/坐标),
右侧详细信息(经纬度/高度/速度/BSSID/飞手距离)。

```bash
cd display-server
pip install -r requirements.txt
python server.py --port COM5        # 连接设备
# 或: python server.py --demo       # 无设备演示模式
# 浏览器打开 http://localhost:8080/dashboard.html
```

高德地图需自行申请 Web 端 JS API Key(免费),配置见 `display-server/dashboard.html`
顶部;未配置时列表/详情仍可用。完整说明见 `display-server/README.md`。

---

## 四、配置说明(`src/config.h`)

| 配置 | 默认 | 说明 |
|------|------|------|
| `RSSI_FILTER_DBM` | `-90` | RSSI 过滤阈值(dBm) |
| `RID_CHANNELS` | `{1, 6, 11}` | 侦听信道轮询列表(国内可加 13) |
| `CHANNEL_DWELL_MS` | `800` | 每信道停留时间 |
| `DRONE_TIMEOUT_MS` | `30000` | 无人机离线判定时间 |
| `MAX_DRONES` | `8` | 最多同时跟踪数量 |
| `FORCE_EXTERNAL_ANTENNA` | `1` | 强制固定外部天线 |
| `ANT_SEL_GPIO0/1` | `14/15` | 天线切换 GPIO(仅带 RF 开关的板子需要) |
| `EXTERNAL_ANT_INDEX` | `0` | 外部天线对应 ANT0/ANT1 |
| `NAV_URL_MODE` | `0` | 0=高德 1=Google 2=geo URI |

---

## 五、硬件注意(重要)

### 1. 关于"强制外部天线"(IPEX→SMA 外置天线用户必读)
- **ESP32-S3-WROOM-1 模块本身没有 RF 天线切换开关**:`-WROOM-1` = 板载 PCB 天线固定,`-WROOM-1U` = 外置 U.FL 天线固定。
- 已核实 LILYGO 官方原理图(`schematic/T_Display_S3.pdf`):T-Display-S3 板上**没有任何天线切换器件/IPEX 座**,天线完全由模块决定。
- 你改装 IPEX→SMA 外置天线(将 IPEX 馈线焊到模块射频馈点)后,**外部天线就是射频通路里的唯一天线**,不存在"内外天线来回切换"的问题——固件里也绝无 AUTO 模式,`esp_wifi_set_ant` 在无开关的模块上返回错误会被忽略,不影响工作。
- 改装建议:焊接 IPEX 馈线时**切断 PCB 天线走线**,否则 PCB 天线与外置天线并联会劣化接收性能。
- 若你后续换用**带 RF 切换开关**的板子/模块,在 `config.h` 填好 `ANT_SEL_GPIO0/1` 与 `EXTERNAL_ANT_INDEX`,固件即强制固定到外部天线(仍然永不 AUTO)。

### 2. 关于"电量"(监测设备自身电量)
- 本固件的电量 = **T-Display-S3 监测设备自己的电池电量**(IO04 ADC,1/2 分压)。
- 电池电压 3.30V~4.20V 映射为 0%~100%;未接电池时读到 TP4056 充电电压(>4.3V),界面显示 **USB**。
- 主页状态栏:电池图标 + 百分比;详情页:本机电量字段。
- 注意:被监测无人机的电量在 ASTM F3411 / CN 46750-2025 标准消息中**均无此字段**,无法被动获取;若你的目标无人机通过厂商私有扩展广播电量,可在 `drone_store.cpp` 中回填 `DroneEntry.battery`(已预留)。

### 3. 关于"纯接收"
本固件不会连接任何 WiFi、不会建立热点、不会发送任何数据帧,因此**不会抬升本机底噪**,也不会对目标无人机产生任何影响。
被动侦听属于合法接收行为,请仅在**法律法规允许的场景**下使用。

---

## 六、支持与解析的协议

| 协议 | 载体 | 说明 |
|------|------|------|
| ASTM F3411-22/22a ODID | WiFi Beacon / Probe Response 厂商 IE(OUI `FA:0B:BC`,类型 0x0D)| 消息包(Message Pack)或单条消息,兼容无计数器的旧式布局与旧 OUI `FA:0B:57` |
| ASTM F3411-19 | WiFi NAN Action 帧 | 复用 `odid_wifi_receive_message_pack_nan_action_frame` |
| CN 46750-2025(国标) | Beacon 内数据包(`0xFF` 头) | `CN46750_FindPacket` + `CN46750_RID_Decode`,含 SN、实名登记号、GCS 位置、无人机位置、速度、高度等 |

---

## 七、工程结构

```
tdisplay-s3-rid-monitor-v1.0/
├── platformio.ini          # 工程配置(TFT_eSPI Setup206 等效参数)
├── tools/
│   └── gen_font.py         # 中文 16x16 点阵字库生成脚本(pip install pillow)
└── src/
    ├── main.cpp            # 入口:屏幕初始化 + 主循环
    ├── config.h            # 全部可配置项
    ├── antenna.cpp/.h      # 强制外部天线(FIXED, 非 AUTO)
    ├── sniffer.cpp/.h      # WiFi promiscuous 纯接收嗅探 + ODID/国标解析
    ├── drone_store.cpp/.h  # 无人机库:增量合并、RSSI 排序、超时老化、机型/品牌识别回填
    ├── drone_models.h      # 识别表: DJI SN 前缀→具体型号 + MAC OUI→品牌(均可扩充)
    ├── buttons.cpp/.h      # 双按键:单击/双击/长按
    ├── ui.cpp/.h           # 界面:主页/二级菜单/详情/二维码 + 中文点阵绘制
    ├── cn_font.h           # 生成的 16x16 中文字库(勿手改,改 UI 文案后重跑 tools/gen_font.py)
    ├── odid/               # libopendroneid (Apache-2.0, Intel)
    ├── odidcn/             # CN 46750-2025 解析器 (Apache-2.0)
    └── qrcodegen/          # Project Nayuki QR Code generator (MIT)
```

## 八、第三方库许可

- `libopendroneid` / `libopendroneidcn`:Apache License 2.0(Copyright Intel Corporation / Jun Zhang),见 `src/odid/LICENSE`、`src/odidcn/LICENSE`
- `qrcodegen`(Project Nayuki):MIT License,https://github.com/nayuki/QR-Code-generator
- `TFT_eSPI`(Bodmer):BSD-3-Clause,通过 PlatformIO 自动下载

## 九、免责声明

本固件仅用于**合法授权**的无人机监测、安全研究、教学与测试场景。请遵守所在国家/地区的无线电与无人机管理法规。
