# Claude Code 中转站切换器

Windows 桌面工具：管理多组服务地址和 Key，选择模型与推理档位，并在指定项目文件夹中启动 Claude Code。

## 下载与准备

1. 打开 [下载页面](https://github.com/huoshwkaba-wq/claude-code-gateway-switcher/releases/latest)，在 Assets 中下载 `ClaudeGatewaySwitcher.exe`，双击运行。此文件是独立程序，无需安装 Python。
2. 使用前请安装 Claude Code，并确认在命令提示符中输入 `claude --version` 能显示版本号。
3. 准备服务商提供的 Anthropic 协议 Base URL、Key 和可用模型 ID。

## 软件功能

- 保存、切换和删除多组服务地址与 Key，首次运行可导入当前 Claude Code 配置。
- 读取模型列表，逐个测试候选模型，多选保存常用模型；双击模型可设为当前模型。
- 进行接口测试和单模型测试，查看测试记录；批量测试可以停止。
- 模型测试在后台运行，不会为每个模型弹出命令窗口。
- 设置推理档位，选择项目文件夹，一键应用配置并启动 Claude Code。
- 启动时优先复用最近使用的 Windows Terminal 窗口，并拦截短时间内的重复点击。
- 对支持读取价格的服务显示模型价格和官方计费入口；其他情况以服务商公布的信息为准。
- 点击 Key 输入框右侧的眼睛查看或隐藏 Key。
- 切换配置或关闭窗口时，提醒处理尚未保存的修改。

## 使用步骤

1. 打开程序，点击左下角 **新增**，填写配置名称、服务地址和 Key，点击 **保存配置**。地址填写服务商提供的 Anthropic 协议 Base URL，不要填写以 `/v1/messages` 结尾的完整接口地址。
2. 点击左侧已保存的配置，程序尝试读取模型列表。如果未能读取，可以在上方模型框手动输入完整模型 ID。
3. 点击 **接口测试** 检查基础接口；选中或输入模型后点击 **单模型测试** 验证实际回复。点击 **测试全部模型** 可逐个测试列表中的候选模型，结果显示在列表和测试记录中。
4. 在下方单击多选需要保存的常用模型，点击 **保存常用模型**；再从上方选择一个当前模型，也可双击列表中的模型设为当前模型。
5. 选择推理档位。建议先用 `auto`；其他档位是否生效由所选模型和 Claude Code 支持情况决定。
6. 点击 **选择文件夹**，选择项目工作目录，再点击 **启用并打开 Claude Code**。程序会保存配置，并在该目录打开 Claude Code。只想保存并应用配置时，可点击 **只应用配置**。

切换配置后，新启动的 Claude Code 会话使用所选设置。重复点击启动按钮会在短时间内合并处理；已打开 Windows Terminal 时，新会话会在最近使用的窗口中新建标签页。模型测试会发送真实请求，可能产生费用；限流或接口不提供模型列表不代表模型一定不可用。批量测试期间请先点击 **停止** 并等待结束，再切换或保存配置。

## 配置与隐私

配置列表中的 Key 使用 Windows 当前账户的 DPAPI 加密。启用时，Claude Code 需要在当前用户的 `~/.claude/settings.json` 中读取 Key；请勿分享该文件。测试记录仅保留在本次程序运行期间。

## 技术与构建

- Python：配置管理、测试和启动逻辑。
- Tkinter：Windows 桌面界面。
- Windows DPAPI：保护本机保存的 Key。
- Python 标准库：JSON 配置、HTTP 请求、进程与文件管理。
- PyInstaller：打包独立 Windows EXE。

在 Windows 上安装 Python 和 PyInstaller 后，在项目目录运行 `python app.py` 启动源码，运行 `python -m unittest -q test_app test_core` 执行测试，运行 `./build.ps1` 打包。
