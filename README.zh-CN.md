# Typecraft

[English](README.md) | 中文

跨平台桌面打字模拟器。粘贴文字后，可以在应用内预览逐字输入，也可以向其他应用输入。支持速度设置、错字与纠正、停顿规则，以及可选的 AI 助手。

## 功能

- 按每秒词数或基础完成分钟数设置速度，显示规则增加的等待时间及预计总时长。
- 模拟节奏变化、错字、退格纠正；支持暂停、继续和停止。
- 中文 / English 界面；两个内置规则预设，可新增、编辑、导入和导出 JSON 配置。
- 外部输入前倒计时 5 秒，按 Esc 停止。
- AI 助手可生成打字方案、润色、翻译或执行自定义文字任务；结果需手动应用，支持撤销上一次应用。
- 每次启动检查依赖，缺失或版本不符时显示安装说明、链接及复制按钮。

## 下载安装

这是 Python 源码应用，尚未提供独立 exe / dmg 安装包。下载仓库 ZIP 后完整解压，保持文件在同一目录。需要 **Python 3.10+、Tkinter/Tcl/Tk 和图形桌面**；建议安装仍受支持的 Python 版本。

| 系统 | 启动方式 |
| --- | --- |
| Windows | 从 [Python 官网](https://www.python.org/downloads/windows/)安装 Python，包含 Tcl/Tk and IDLE，然后双击 `Start Windows.bat`。 |
| macOS | 安装含 Tcl/Tk 的 [Python](https://www.python.org/downloads/macos/)，运行 `Start macOS.command`；必要时先执行 `chmod +x "Start macOS.command"`。 |
| Linux | 在项目目录执行 `sh start-linux.sh`。Ubuntu / Debian / Linux Mint 缺少 Tkinter 时，执行 `sudo apt install python3-tk`。 |

也可以直接运行 `python3 typecraft.py`（Windows：`py -3 typecraft.py`）。启动器优先使用项目内的 `.venv`，直接运行 Python 命令则使用你指定的解释器。

### 启动检查

检查 Python 版本、Tkinter/Tcl/Tk、SSL、pynput 版本及外部输入后端。全部通过时直接进入主界面；可选组件有问题时仍可进入预览，必需组件不可用时需先修复。安装或授权后重新启动即可复查。检查不联网、不自动安装、不发送按键。

缺少 Python 或 Tkinter 时尝试使用系统原生弹窗。Linux 需要 `zenity` 或 `xmessage`；两者都没有或没有图形桌面时，只能在终端查看说明。文件管理器双击脚本无反应时，请在终端运行 `sh start-linux.sh`。

### 启用外部输入

应用内预览无需第三方 Python 包。外部输入需要 `requirements.txt` 中的 pynput。在项目目录安装：

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS / Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

安装后重新打开启动脚本。Ubuntu / Debian 创建环境可能需要 `sudo apt install python3-venv`；若 evdev 编译失败，可能需要 `sudo apt install build-essential python3-dev`。

## 使用方法

1. 粘贴文字，选择速度或基础完成时间。
2. 在预览中检查规则、节奏和预计总时长。
3. 如需输入其他应用，选择外部输入并点击开始，在 5 秒倒计时内点选目标文本框。
4. 通过暂停、停止按钮控制输入；外部输入可按 Esc 停止。

速度中的一个“词”按 5 个字符计算，包括空格；它不等于中文词数或空格分隔的单词统计。自定义规则等待时间会增加总时长。倒计时、手动暂停和系统延迟不计入基础时间，完成时间不是实时保证。

外部输入跟随键盘焦点，Enter / Tab 会发送真实按键，可能提交表单或切换焦点。建议先在空白文本编辑器里试运行。停止不会删除已输入到其他应用的内容。

## 规则与 AI

- [中文规则说明](RULES.zh-CN.md)：错字、纠正、等待时长、导入和导出。
- [AI 使用说明](AI.zh-CN.md)：兼容的 Chat Completions 接口、密钥、生成和应用结果。
- [完整英文说明](README.md)：控件、计时规则及输入细节。

普通打字与预览不联网。只有主动调用 AI 时，AI 页文字和指令才会发送给你配置的服务商，可能产生服务商费用。密钥只保留在当前会话，不写入设置。取消请求会忽略迟到的结果，不保证服务端取消计费。

界面语言、已应用规则和不含密钥的连接设置保存在 `user_data/settings.json`。规则中可能包含用户自定义文字；此目录不应提交到 Git。原文不会自动保存。

## 已知限制

- Linux 外部输入需要 X11，不支持 Wayland；预览仍可使用。
- macOS 需要给予运行 Python 的程序辅助功能 / 输入监控权限，授权后重启。
- Windows 的受保护或以管理员身份运行的目标可能拒绝模拟输入。
- Linux X11 实测出现过中文退格纠正后字符不正确；中文外部输入尚不能保证准确。预览支持 Unicode。
- 目标应用的自动纠正、缩进、输入法和快捷键可能改变输出；预览不是目标应用内容的回读。
- 当前已在 Linux 测试；Windows / macOS 尚未实机验证。真实 AI 服务商调用也尚未验证。

## 项目结构与验证范围

`typecraft.py` 为界面入口，`startup.py` 检查依赖，`engine.py` 生成输入计划，`rules.py` / `rules_page.py` 处理规则，`ai_*.py` 处理 AI，`keyboard_output.py` 负责外部输入。预设位于 `presets/`。

发布前在 Linux、Python 3.12、Tk 8.6 和隔离 X11 显示环境中完成 94 项自动化测试。测试覆盖输入计划、规则、界面、AI 请求处理和启动检查。测试代码和测试记录仅保留在本地，不包含在公开仓库中。
