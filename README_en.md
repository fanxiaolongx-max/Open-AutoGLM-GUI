# Open-AutoGLM

[中文阅读.](./README.md)

<div align="center">
<img src="resources/logo.svg" width="20%"/>
</div>

<p align="center">
    👋 Join our <a href="resources/WECHAT.md" target="_blank">WeChat</a> or <a href="https://discord.gg/QR7SARHRxK" target="_blank">Discord</a> communities
</p>

---

## Table of Contents

- [Introduction](#introduction)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Web Interface](#web-interface)
  - [Telegram Bot](#telegram-bot)
  - [Command Line (CLI)](#command-line-cli)
  - [Python API](#python-api)
- [Environment Setup](#environment-setup)
- [Model Service](#model-service)
- [Remote Debugging](#remote-debugging)
- [Supported Apps](#supported-apps)
- [FAQ](#faq)
- [Citation](#citation)

---

## Introduction

Open-AutoGLM is a **mobile intelligent assistant framework** based on vision-language models. It understands phone screen content and automatically executes operations. Users simply describe their needs in natural language, such as "Open eBay and search for wireless earphones", and the system will automatically complete the entire workflow.

### How It Works

```
User Command → Screenshot → AI Understands Interface → Generate Action → Execute → Loop Until Complete
```

### Supported Devices

| Device Type | Connection | Web Interface | CLI |
|-------------|------------|:-------------:|:---:|
| **Android** | ADB | ✅ | ✅ |
| **HarmonyOS** | HDC | ❌ | ✅ |
| **iOS** | WebDriverAgent | ❌ | ✅ |

> 💡 Web interface currently only supports Android. For HarmonyOS and iOS, use CLI.

---

## Key Features

### Two Ways to Use

| Method | Command | Use Case |
|--------|---------|----------|
| **🌐 Web Server** | `python run_web.py` | Browser access, multi-user, remote control |
| **⌨️ Command Line** | `python main.py` | Script automation, development/debugging |

### Core Features

- 🤖 **AI-Powered** - Based on AutoGLM vision-language model, intelligently understands screen content
- 📱 **Multi-Device Support** - Manage Android, HarmonyOS, and iOS devices simultaneously
- 🤖 **Telegram Bot** - Remote control, send tasks anytime, anywhere
- ⏰ **Scheduled Tasks** - Support one-time, daily, and weekly automatic execution
- 📧 **Email Reports** - Automatic execution reports after complex tasks
- 🔧 **Rule Engine** - Custom app mappings, action rules, and prompts
- 🌐 **Remote Debugging** - WiFi wireless connection and QR code pairing
- 📊 **Real-time Preview** - Live phone screen display during task execution
- 💾 **Data Persistence** - SQLite database stores sessions and message history

---

## Quick Start

### 1. Install Dependencies

```bash
# Clone repository
git clone https://github.com/zai-org/Open-AutoGLM.git
cd Open-AutoGLM

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### 2. Connect Device

**Android Device:**
```bash
# Enable USB debugging on phone, connect via data cable
adb devices
# Should show: List of devices attached
#             XXXXXXXX    device
```

**HarmonyOS Device:**
```bash
hdc list targets
```

**iOS Device:**
See [iOS Setup Guide](docs/ios_setup/ios_setup.md)

### 3. Start Application

```bash
# Option 1: Web Server (Recommended)
python run_web.py

# Option 2: Command Line
python main.py --base-url https://open.bigmodel.cn/api/paas/v4 --model autoglm-phone --apikey YOUR_API_KEY
```

After starting, visit http://localhost:8080

---

## Usage

### Web Interface

The Web server provides a complete management interface with multi-user remote access support.

```bash
# Default start (port 8080)
python run_web.py

# Custom configuration
python run_web.py --host 0.0.0.0 --port 8000

# Development mode (auto-reload)
python run_web.py --reload
```

#### Features

| Module | Description |
|--------|-------------|
| **Dashboard** | System dashboard showing device status, model config, task stats |
| **Device Center** | Manage device connections, USB, WiFi, QR pairing |
| **Model Service** | Configure and switch between AI model services |
| **Chat Execution** | Select device, input task description, AI auto-executes |
| **Scheduled Tasks** | Create scheduled or periodic automation tasks |
| **Rule Management** | Manage app mappings, action rules, and system prompts |

#### Access URLs

| URL | Description |
|-----|-------------|
| `http://localhost:8080` | Web Interface |
| `http://localhost:8080/docs` | API Documentation (Swagger) |
| `http://localhost:8080/redoc` | API Documentation (ReDoc) |

---

### Telegram Bot

Control your phone remotely via Telegram Bot, send tasks anytime, anywhere.

#### Setup

1. **Create Bot**: Find @BotFather in Telegram, send `/newbot` to create a bot
2. **Get Token**: BotFather will return a Bot Token
3. **Configure**: Enter the Token and Chat ID in Web interface system settings

#### Supported Features

| Feature | Description |
|---------|-------------|
| 📱 **Device Management** | View device status, screenshots, select devices |
| 🤖 **Task Execution** | Send text messages directly to execute tasks |
| ⏰ **Scheduled Tasks** | View and manage scheduled tasks |
| 📊 **Model Config** | Select AI model, adjust parameters |
| ⚙️ **System Settings** | Email notifications, system diagnostics |
| 📈 **Statistics** | View usage statistics |

#### Usage Examples

```
/start          - Start Bot, show main menu
/devices        - View connected devices
/screenshot     - Get current device screenshot
Open WhatsApp   - Send task command directly
```

---

### Command Line (CLI)

Command line is suitable for script automation and quick testing.

```bash
# Interactive mode
python main.py --base-url http://localhost:8000/v1 --model autoglm-phone-9b-multilingual

# Execute single task
python main.py --base-url http://localhost:8000/v1 "Open Maps and search for nearby coffee shops"

# Use API Key
python main.py --apikey sk-xxxxx "Open WhatsApp and send a message"

# HarmonyOS device
python main.py --device-type hdc "Open Settings"

# iOS device
python main.py --device-type ios --wda-url http://localhost:8100 "Open Safari"

# List supported apps
python main.py --list-apps
```

#### Common Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--base-url` | Model API URL | `http://localhost:8000/v1` |
| `--model` | Model name | `autoglm-phone-9b` |
| `--apikey` | API key | `EMPTY` |
| `--device-type` | Device type (`adb`/`hdc`/`ios`) | `adb` |
| `--device-id` | Specify device ID | Auto-detect |
| `--lang` | Language (`cn`/`en`) | `en` |
| `--max-steps` | Maximum execution steps | `100` |

---

### Python API

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig

# Configure model
model_config = ModelConfig(
    base_url="https://open.bigmodel.cn/api/paas/v4",
    model_name="autoglm-phone",
    api_key="your-api-key",
)

# Create Agent
agent = PhoneAgent(model_config=model_config)

# Execute task
result = agent.run("Open eBay and search for wireless earphones")
print(result)
```

---

## Environment Setup

### Android Device

1. **Enable Developer Mode**
   - Settings → About Phone → Tap Build Number 7 times

2. **Enable USB Debugging**
   - Settings → Developer Options → USB Debugging ✓
   - Some devices also need "USB Debugging (Security Settings)"

3. **Install ADB Tools**
   ```bash
   # macOS
   brew install android-platform-tools

   # Verify installation
   adb version
   ```

4. **Install ADB Keyboard** (for text input)
   - Download [ADBKeyboard.apk](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk)
   - Enable it in system settings after installation

### HarmonyOS Device

1. Enable Developer Mode and USB Debugging
2. Download [HDC Tool](https://developer.huawei.com/consumer/en/download/)
3. Configure PATH environment variable

### iOS Device

See [iOS Setup Guide](docs/ios_setup/ios_setup.md)

---

## Model Service

### Use Third-Party Services (Recommended)

No local GPU needed, use cloud models directly:

**z.ai:**
```bash
python main.py \
  --base-url https://api.z.ai/api/paas/v4 \
  --model autoglm-phone-multilingual \
  --apikey YOUR_API_KEY \
  "Open Chrome browser"
```

**Novita AI:**
```bash
python main.py \
  --base-url https://api.novita.ai/openai \
  --model zai-org/autoglm-phone-9b-multilingual \
  --apikey YOUR_API_KEY \
  "Open Chrome browser"
```

### Local Model Deployment

Requires NVIDIA GPU with 24GB+ VRAM:

```bash
# Using vLLM
python3 -m vllm.entrypoints.openai.api_server \
  --served-model-name autoglm-phone-9b-multilingual \
  --model zai-org/AutoGLM-Phone-9B-Multilingual \
  --port 8000
```

### Model Downloads

| Model | Download Links |
|-------|----------------|
| AutoGLM-Phone-9B | [Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B) / [ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B) |
| AutoGLM-Phone-9B-Multilingual | [Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B-Multilingual) / [ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B-Multilingual) |

---

## Remote Debugging

Connect devices wirelessly via WiFi, no USB cable needed.

### Android Device

```bash
# 1. Enable Wireless Debugging on phone (Settings → Developer Options → Wireless Debugging)
# 2. Get phone IP and port
# 3. Connect from computer
adb connect 192.168.1.100:5555

# Verify connection
adb devices
```

### HarmonyOS Device

```bash
hdc tconn 192.168.1.100:5555
hdc list targets
```

---

## Supported Apps

### Android (50+ Apps)

| Category | Apps |
|----------|------|
| Social | X, TikTok, WhatsApp, Telegram, Instagram |
| Shopping | Amazon, eBay, Temu |
| Productivity | Gmail, Google Calendar, Google Drive |
| Travel | Google Maps, Booking.com, Expedia |
| Media | Chrome, YouTube, Google Play |

Run `python main.py --list-apps` to see the complete list.

### HarmonyOS (60+ Apps)

Run `python main.py --device-type hdc --list-apps` to see the complete list.

---

## Available Actions

| Action | Description |
|--------|-------------|
| `Launch` | Launch an app |
| `Tap` | Tap at coordinates |
| `Type` | Input text |
| `Swipe` | Swipe screen |
| `Back` | Go back |
| `Home` | Return to home screen |
| `Long Press` | Long press |
| `Double Tap` | Double tap |
| `Wait` | Wait for page to load |
| `Take_over` | Request manual takeover |

---

## Project Structure

```
Open-AutoGLM/
├── run_web.py           # Web server entry
├── main.py              # CLI entry
├── phone_agent/         # Agent core module
│   ├── agent.py         # PhoneAgent main class
│   ├── adb/             # Android ADB utilities
│   ├── hdc/             # HarmonyOS HDC utilities
│   ├── xctest/          # iOS WebDriverAgent
│   ├── actions/         # Action executors
│   ├── config/          # Config (app mappings, prompts)
│   └── model/           # AI model client
├── web_app/             # Web server
│   ├── main.py          # FastAPI application
│   ├── routers/         # API routes
│   ├── services/        # Business services
│   │   ├── telegram_bot.py  # Telegram Bot integration
│   │   ├── scheduler_service.py  # Scheduled tasks
│   │   └── email_service.py  # Email service
│   ├── models/          # Data models and database
│   └── static/          # Static resources (Web UI)
└── examples/            # Usage examples
```

---

## FAQ

### Device Not Found

```bash
# Restart ADB service
adb kill-server
adb start-server
adb devices
```

Check:
- Is USB debugging enabled?
- Does the cable support data transfer?
- Did you tap "Allow USB debugging" on phone?

### Can Open Apps But Cannot Tap

Enable **Settings → Developer Options → USB Debugging (Security Settings)**

### Text Input Not Working

Ensure ADB Keyboard is installed and enabled in system settings.

### Telegram Bot Not Responding

1. Check if Bot Token is correct
2. Confirm Chat ID is configured correctly
3. Ensure server can access Telegram API (may need proxy)

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PHONE_AGENT_BASE_URL` | Model API URL | `http://localhost:8000/v1` |
| `PHONE_AGENT_MODEL` | Model name | `autoglm-phone-9b` |
| `PHONE_AGENT_API_KEY` | API key | `EMPTY` |
| `PHONE_AGENT_MAX_STEPS` | Maximum steps | `100` |
| `PHONE_AGENT_DEVICE_TYPE` | Device type | `adb` |
| `PHONE_AGENT_LANG` | Language | `en` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | - |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | - |

---

## Citation

If you find our work helpful, please cite the following papers:

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

## License

This project is licensed under Apache 2.0. See [LICENSE](LICENSE) file.

> ⚠️ **Disclaimer**: This project is for research and learning purposes only. It is strictly prohibited to use for illegal information acquisition, system interference, or any illegal activities. Please review the [Terms of Use](resources/privacy_policy_en.txt).
