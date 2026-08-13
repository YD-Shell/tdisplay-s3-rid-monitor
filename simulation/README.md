# T-Display-S3 RID 监测固件 · 屏幕模拟器

本目录由 `gen_sim.py` 自动生成，用于**像素级模拟**固件在
LILYGO T-Display-S3 上的显示效果。

> 当前版本对应固件 **v3 UI**：**屏幕旋转 90° 竖屏(170×320, rotation 0)**，
> 全部页面竖向布局(参考"必胜RID侦测器"App 风格：深海军蓝底 + 蓝色渐变
> 标题栏 + 暗红机型横幅 + 青色数值 + 状态指示条)，并内置
> **DJI SN→型号 + MAC OUI→品牌** 识别。

## 内容

| 文件 | 说明 |
|------|------|
| `simulator.html` | **交互式模拟器**（自包含单文件，浏览器直接打开） |
| `screens/*.png` | 各页面静态截图（510×960，3 倍放大） |
| `screens/native/*.png` | 原生 170×320 像素截图 |
| `gen_sim.py` | 生成器脚本（镜像 `src/ui.cpp` v3 + `src/drone_models.h`） |
| `verify_screens.py` | 截图关键像素自动校验 |

## 模拟器用法

直接双击打开 `simulator.html`（无需联网）：

- **A 键**（BOOT）：按住 0.8s = 长按；快速点两下 = 双击；单击 = 单击
- **B 键**（IO14）：返回
- 也可用键盘：`A` 单击 / `S` 长按 / `D` 双击 / `B` 返回
- 右侧面板：切换无人机数量场景、本机电池电量、RSSI 实时抖动（500ms）、
  信道轮询（CH:1→6→11，800ms/信道，与固件一致）

按键状态机、页面流转、自动回主页、滚动跟随焦点等行为与
`src/ui.cpp` 完全一致。示例数据使用**真实 DJI SN 前缀**
（如 `1581F45Q...` → DJI Mavic 3）与 **IEEE 注册 MAC OUI**
（如 `18:D7:93:6...` → 道通无人机）。

## 保真度说明

- **中文字库**：直接解析固件 `src/cn_font.h` 的真实 16×16 点阵数据
  （503 字，与烧录进单片机的完全同源）
- **ASCII**：与字库同字体（SimHei 16px 阈值化）生成的 8×16 点阵
- **配色/布局**：逐行复刻 `ui.cpp` v3（竖屏坐标、RGB565 精确转换）
- **识别表**：与固件 `src/drone_models.h` 同一张表
- **二维码**：`https://uri.amap.com/marker?position=经度,纬度`（高德导航，
  NAV_URL_MODE=0），由标准 qrcode 库生成，手机可扫。
  注意：固件端使用 qrcodegen（ECC-M），掩码选择与 Python qrcode 库可能不同，
  两者均为合法二维码，仅图案细节略有差异。
- **屏幕外裁剪**：与 TFT_eSPI 一致，超出屏幕的像素会被裁掉，模拟器同样处理。

## 重新生成

```bash
python gen_sim.py
python verify_screens.py   # 校验截图
```

依赖：`pillow`、`qrcode`（仅生成器需要；HTML 模拟器本身无任何依赖）。


