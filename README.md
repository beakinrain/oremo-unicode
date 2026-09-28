# OREMO Unicode 版 (3.0-b190106-U1)

UTAU 音源录音软件 **OREMO 3.0-b190106** 的完全重写版（Python + Tk）。
在保持原版界面、功能、设置窗口和文件格式兼容的前提下，解决了原版在简体中文
Windows 上的乱码问题。

- 原作者：nwp8861 — http://nwp8861.web.fc2.com/soft/oremo/
- 许可证：**GNU GPL v2**（与原版相同，全文见 [LICENSE](LICENSE)）

## 修改声明 (GPL v2 §2(a))

本仓库中的程序是基于 OREMO 3.0-b190106（© nwp8861，GPL）的修改作品，
于 2026 年 9 月由原 Tcl/Tk + Snack 源码重写为 Python 实现。主要修改：

- 全部改为 Unicode 处理；录音表 / 备注 / BGM 设置 / ust 读取时自动识别编码
  （BOM、UTF-8、UTF-16、Shift_JIS、GBK、Big5），写出编码可设置（默认 Shift_JIS）
- 内置文字编码 / 乱码文件名转换工具
- 以 PortAudio (sounddevice) 与 numpy 取代 Snack 及外部工具
  （oremo-recorder / oremo-player / modifyPre / SPTK）
- 原版缺陷修正 F01–F16（可在「工具 → BUG修正设置」中逐项关闭，关闭即与原版行为一致）
- 新增：高 DPI 显示、界面缩放、面板高度与列表宽度的拖动调整、录音时实时显示、
  字体自动选择、日语 / 简体中文 / English 界面

`res/` 下的录音表、引导 BGM、手册及 `res/message/ja` 的日语文本取自原版发布包。

详细说明见 [res/README-Unicode版说明.txt](res/README-Unicode版说明.txt)。

## 目录

| 路径 | 内容 |
|---|---|
| `src/oremo/` | 程序源码 |
| `src/oremo_main.py`, `src/korede_main.py` | OREMO / KOREDE 启动入口 |
| `res/` | 随程序发布的资源（录音表、BGM、界面文字、许可证等） |
| `oremo.spec`, `build.ps1` | Windows 打包脚本 (PyInstaller) |

## 运行与构建 (Windows)

需要 Python 3.10 以上（含 tkinter）：

```
pip install numpy sounddevice pyinstaller
python src/oremo_main.py          # 直接运行
powershell -File build.ps1        # 打包到 dist/OREMO
```

## macOS 版 (Apple Silicon)

由 GitHub Actions 在云端 Mac 上自动测试并打包（见 `.github/workflows/build.yml`、
`oremo-mac.spec`）。每次推送后，在仓库的 Actions 页面下载 `OREMO-mac-arm64`（.dmg）；
推送 `v*` 标签时会发布到 Releases。安装与首次打开的方法见
[packaging/mac/使用说明-Mac.txt](packaging/mac/使用说明-Mac.txt)。

Mac 版的差异：设置文件保存在 `~/Library/Application Support/OREMO/`，默认录音文件夹为
`~/Documents/OREMO/result`；⌘P / ⌘F / ⌘Q；右键 = 双指点按或 Control+单击；
文件名的 NFD（拆开的浊点）自动统一为 NFC。

## 测试

```
python tests/smoke_test.py zh_CN
```
使用虚拟音频设备，不会使用真实的麦克风和扬声器。

## 第三方组件

打包后的程序包含以下组件，均为 GPL v2 兼容许可：
Python (PSF License)、Tcl/Tk (BSD 风格)、numpy (BSD)、
python-sounddevice (MIT)、PortAudio (MIT)。
原版所用组件的许可证保存在 `res/Licenses/`。
