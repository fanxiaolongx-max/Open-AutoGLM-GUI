# Open-AutoGLM

[Readme in English](README_EN.md)

<div align="center">
<img src="resources/logo.svg" width="20%"/>
</div>

<p align="center">
    👋 加入我们的 <a href="resources/WECHAT.md" target="_blank">微信</a> 社区
</p>
<p align="center">
    🎤 在我们的产品 <a href="https://autoglm.zhipuai.cn/autotyper/" target="_blank">智谱 AI 输入法</a> 体验"用嘴发指令"
</p>

---

## 目录

- [项目简介](#项目简介)
- [主要特性](#主要特性)
- [快速开始](#快速开始)
- [使用方式](#使用方式)
  - [Web 界面](#web-界面)
  - [Telegram Bot](#telegram-bot)
  - [命令行 (CLI)](#命令行-cli)
  - [Python API](#python-api)
- [环境配置](#环境配置)
- [模型服务](#模型服务)
- [远程调试](#远程调试)
- [支持的应用](#支持的应用)
- [常见问题](#常见问题)
- [引用](#引用)

---

## 项目简介

Open-AutoGLM 是一个基于视觉语言模型的**手机智能助理框架**，能够理解手机屏幕内容并自动执行操作。用户只需用自然语言描述需求，如"打开小红书搜索美食"，系统即可自动完成整个操作流程。

### 工作原理

```
用户指令 → 截取屏幕 → AI 理解界面 → 生成操作 → 执行动作 → 循环直到完成
```

### 支持的设备

| 设备类型 | 连接方式 | Web 界面 | CLI 命令行 |
|---------|---------|:--------:|:----------:|
| **Android** | ADB | ✅ | ✅ |
| **HarmonyOS** | HDC | ❌ | ✅ |
| **iOS** | WebDriverAgent | ❌ | ✅ |

> 💡 Web 界面目前仅支持 Android 设备，鸿蒙和 iOS 请使用命令行

---

## 主要特性

### 两种使用方式

| 方式 | 启动命令 | 适用场景 |
|-----|---------|---------| 
| **🌐 Web 服务器** | `python run_web.py` | 浏览器访问、多用户、远程控制 |
| **⌨️ 命令行** | `python main.py` | 脚本自动化、开发调试 |

### 核心功能

- 🤖 **AI 驱动** - 基于 AutoGLM 视觉语言模型，智能理解屏幕内容
- 📱 **多设备支持** - 同时管理 Android、HarmonyOS、iOS 设备
- 🤖 **Telegram Bot** - 远程控制，随时随地发送任务
- ⏰ **定时任务** - 支持单次、每日、每周自动执行
- 📧 **邮件报告** - 复杂任务完成后自动发送执行报告
- 🔧 **规则引擎** - 自定义应用映射、动作规则和提示词
- 🌐 **远程调试** - WiFi 无线连接和二维码配对
- 📊 **实时预览** - 任务执行时实时显示手机屏幕
- 💾 **数据持久化** - SQLite 数据库存储会话和消息历史

---

## 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/zai-org/Open-AutoGLM.git
cd Open-AutoGLM

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
pip install -e .
```

### 2. 连接设备

**Android 设备：**
```bash
# 开启手机的 USB 调试，用数据线连接
adb devices
# 应显示: List of devices attached
#         XXXXXXXX    device
```

**鸿蒙设备：**
```bash
hdc list targets
```

**iOS 设备：**
参考 [iOS 配置指南](docs/ios_setup/ios_setup.md)

### 3. 启动应用

```bash
# 方式一：Web 服务器（推荐）
python run_web.py

# 方式二：命令行
python main.py --base-url https://open.bigmodel.cn/api/paas/v4 --model autoglm-phone --apikey YOUR_API_KEY
```

启动后访问 http://localhost:8080

---

## 使用方式

### Web 界面

Web 服务器提供完整的管理界面，支持多用户远程访问。

```bash
# 默认启动（端口 8080）
python run_web.py

# 自定义配置
python run_web.py --host 0.0.0.0 --port 8000

# 开发模式（自动重载）
python run_web.py --reload
```

#### 功能模块

| 模块 | 功能说明 |
|------|----------|
| **控制台** | 系统仪表盘，显示设备状态、模型配置、任务统计 |
| **设备中心** | 管理设备连接，支持 USB、WiFi、二维码配对 |
| **模型服务** | 配置和切换多个 AI 模型服务 |
| **对话执行** | 选择设备、输入任务描述，AI 自动执行 |
| **定时任务** | 创建定时或周期性自动化任务 |
| **规则管理** | 管理应用映射、动作规则和系统提示词 |

#### 启动后访问

| 地址 | 说明 |
|-----|------|
| `http://localhost:8080` | Web 界面 |
| `http://localhost:8080/docs` | API 文档 (Swagger) |
| `http://localhost:8080/redoc` | API 文档 (ReDoc) |

---

### Telegram Bot

通过 Telegram Bot 远程控制手机，随时随地发送任务。

#### 配置步骤

1. **创建 Bot**: 在 Telegram 中找到 @BotFather，发送 `/newbot` 创建机器人
2. **获取 Token**: BotFather 会返回 Bot Token
3. **配置**: 在 Web 界面的系统设置中填入 Token 和 Chat ID

#### 支持的功能

| 功能 | 说明 |
|------|------|
| 📱 **设备管理** | 查看设备状态、截图、选择操作设备 |
| 🤖 **任务执行** | 直接发送文本消息执行任务 |
| ⏰ **定时任务** | 查看和管理定时任务 |
| 📊 **模型配置** | 选择 AI 模型、调整参数 |
| ⚙️ **系统设置** | 邮件通知、系统诊断 |
| 📈 **统计信息** | 查看使用统计 |

#### 使用示例

```
/start          - 启动 Bot，显示主菜单
/devices        - 查看已连接设备
/screenshot     - 获取当前设备截图
打开微信        - 直接发送任务指令
```

---

### 命令行 (CLI)

命令行适合脚本自动化和快速测试。

```bash
# 交互模式
python main.py --base-url http://localhost:8000/v1 --model autoglm-phone-9b

# 执行单个任务
python main.py --base-url http://localhost:8000/v1 "打开美团搜索附近的火锅店"

# 使用 API Key
python main.py --apikey sk-xxxxx "打开微信发消息给文件传输助手"

# 鸿蒙设备
python main.py --device-type hdc "打开设置"

# iOS 设备
python main.py --device-type ios --wda-url http://localhost:8100 "打开 Safari"

# 查看支持的应用
python main.py --list-apps
```

#### 常用参数

| 参数 | 说明 | 默认值 |
|-----|------|-------|
| `--base-url` | 模型 API 地址 | `http://localhost:8000/v1` |
| `--model` | 模型名称 | `autoglm-phone-9b` |
| `--apikey` | API 密钥 | `EMPTY` |
| `--device-type` | 设备类型 (`adb`/`hdc`/`ios`) | `adb` |
| `--device-id` | 指定设备 ID | 自动检测 |
| `--lang` | 语言 (`cn`/`en`) | `cn` |
| `--max-steps` | 最大执行步数 | `100` |

---

### Python API

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig

# 配置模型
model_config = ModelConfig(
    base_url="https://open.bigmodel.cn/api/paas/v4",
    model_name="autoglm-phone",
    api_key="your-api-key",
)

# 创建 Agent
agent = PhoneAgent(model_config=model_config)

# 执行任务
result = agent.run("打开淘宝搜索无线耳机")
print(result)
```

---

## 环境配置

### Android 设备

1. **开启开发者模式**
   - 设置 → 关于手机 → 连续点击版本号 7 次

2. **开启 USB 调试**
   - 设置 → 开发者选项 → USB 调试 ✓
   - 部分机型还需开启 "USB 调试（安全设置）"

3. **安装 ADB 工具**
   ```bash
   # macOS
   brew install android-platform-tools

   # 验证安装
   adb version
   ```

4. **安装 ADB Keyboard**（用于中文输入）
   - 下载 [ADBKeyboard.apk](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk)
   - 安装后在设置中启用

### 鸿蒙设备

1. 开启开发者模式和 USB 调试
2. 下载 [HDC 工具](https://developer.huawei.com/consumer/cn/download/)
3. 配置 PATH 环境变量

### iOS 设备

参考 [iOS 环境配置指南](docs/ios_setup/ios_setup.md)

---

## 模型服务

### 使用第三方服务（推荐）

无需本地 GPU，直接使用云端模型：

**智谱 BigModel：**
```bash
python main.py \
  --base-url https://open.bigmodel.cn/api/paas/v4 \
  --model autoglm-phone \
  --apikey YOUR_API_KEY \
  "打开微信"
```

**ModelScope（魔搭社区）：**
```bash
python main.py \
  --base-url https://api-inference.modelscope.cn/v1 \
  --model ZhipuAI/AutoGLM-Phone-9B \
  --apikey YOUR_API_KEY \
  "打开微信"
```

### 本地部署模型

需要 24GB+ 显存的 NVIDIA GPU：

```bash
# 使用 vLLM
python3 -m vllm.entrypoints.openai.api_server \
  --served-model-name autoglm-phone-9b \
  --model zai-org/AutoGLM-Phone-9B \
  --port 8000
```

### 模型下载

| 模型 | 下载地址 |
|-----|---------|
| AutoGLM-Phone-9B | [Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B) / [ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B) |
| AutoGLM-Phone-9B-Multilingual | [Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B-Multilingual) / [ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B-Multilingual) |

---

## 远程调试

支持通过 WiFi 无线连接设备，无需 USB 数据线。

### Android 设备

```bash
# 1. 手机开启无线调试（设置 → 开发者选项 → 无线调试）
# 2. 获取手机 IP 和端口
# 3. 电脑端连接
adb connect 192.168.1.100:5555

# 验证连接
adb devices
```

### 鸿蒙设备

```bash
hdc tconn 192.168.1.100:5555
hdc list targets
```

---

## 支持的应用

### Android（50+ 款）

| 分类 | 应用 |
|------|-----|
| 社交通讯 | 微信、QQ、微博 |
| 电商购物 | 淘宝、京东、拼多多 |
| 美食外卖 | 美团、饿了么 |
| 出行旅游 | 携程、12306、滴滴 |
| 视频娱乐 | bilibili、抖音、爱奇艺 |
| 音乐音频 | 网易云音乐、QQ音乐 |
| 内容社区 | 小红书、知乎、豆瓣 |

### 鸿蒙（60+ 款）

运行 `python main.py --device-type hdc --list-apps` 查看完整列表。

---

## 可用操作

| 操作 | 描述 |
|-----|------|
| `Launch` | 启动应用 |
| `Tap` | 点击指定坐标 |
| `Type` | 输入文本 |
| `Swipe` | 滑动屏幕 |
| `Back` | 返回上一页 |
| `Home` | 返回桌面 |
| `Long Press` | 长按 |
| `Double Tap` | 双击 |
| `Wait` | 等待页面加载 |
| `Take_over` | 请求人工接管 |

---

## 项目结构

```
Open-AutoGLM/
├── run_web.py           # Web 服务器入口
├── main.py              # 命令行入口
├── phone_agent/         # Agent 核心模块
│   ├── agent.py         # PhoneAgent 主类
│   ├── adb/             # Android ADB 工具
│   ├── hdc/             # 鸿蒙 HDC 工具
│   ├── xctest/          # iOS WebDriverAgent
│   ├── actions/         # 操作执行器
│   ├── config/          # 配置（应用映射、提示词）
│   └── model/           # AI 模型客户端
├── web_app/             # Web 服务器
│   ├── main.py          # FastAPI 应用
│   ├── routers/         # API 路由
│   ├── services/        # 业务服务
│   │   ├── telegram_bot.py  # Telegram Bot 集成
│   │   ├── scheduler_service.py  # 定时任务
│   │   └── email_service.py  # 邮件服务
│   ├── models/          # 数据模型和数据库
│   └── static/          # 静态资源（Web UI）
└── examples/            # 使用示例
```

---

## 常见问题

### 设备未找到

```bash
# 重启 ADB 服务
adb kill-server
adb start-server
adb devices
```

检查项：
- USB 调试是否开启
- 数据线是否支持数据传输
- 手机是否点击了"允许 USB 调试"

### 能打开应用但无法点击

开启 **设置 → 开发者选项 → USB 调试（安全设置）**

### 文本输入不工作

确保 ADB Keyboard 已安装并在系统设置中启用。

### Windows 编码异常

```bash
set PYTHONIOENCODING=utf-8
python main.py ...
```

### Telegram Bot 无响应

1. 检查 Bot Token 是否正确
2. 确认 Chat ID 配置正确
3. 确保服务器能访问 Telegram API（可能需要代理）

---

## 环境变量

| 变量 | 描述 | 默认值 |
|-----|------|-------|
| `PHONE_AGENT_BASE_URL` | 模型 API 地址 | `http://localhost:8000/v1` |
| `PHONE_AGENT_MODEL` | 模型名称 | `autoglm-phone-9b` |
| `PHONE_AGENT_API_KEY` | API 密钥 | `EMPTY` |
| `PHONE_AGENT_MAX_STEPS` | 最大步数 | `100` |
| `PHONE_AGENT_DEVICE_TYPE` | 设备类型 | `adb` |
| `PHONE_AGENT_LANG` | 语言 | `cn` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | - |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | - |

---

## 引用

如果你觉得我们的工作有帮助，请引用以下论文：

```bibtex
@article{liu2024autoglm,
  title={Autoglm: Autonomous foundation agents for guis},
  author={Liu, Xiao and Qin, Bo and Liang, Dongzhu and others},
  journal={arXiv preprint arXiv:2411.00820},
  year={2024}
}

@article{xu2025mobilerl,
  title={MobileRL: Online Agentic Reinforcement Learning for Mobile GUI Agents},
  author={Xu, Yifan and Liu, Xiao and others},
  journal={arXiv preprint arXiv:2509.18119},
  year={2025}
}
```

---

## 许可证

本项目采用 Apache 2.0 许可证。详见 [LICENSE](LICENSE) 文件。

> ⚠️ **免责声明**：本项目仅供研究和学习使用。严禁用于非法获取信息、干扰系统或任何违法活动。请仔细审阅 [使用条款](resources/privacy_policy.txt)。
