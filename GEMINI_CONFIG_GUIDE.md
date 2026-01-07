# Gemini API 配置指南

## 概述

AutoGLM现已支持Google Gemini API，通过Antigravity代理提供访问服务。Gemini是Google开发的大型语言模型，具有强大的多模态能力和推理能力。

## 配置信息

### 预置配置

系统已预置了Gemini API配置，用户可以直接使用：

- **服务名称**: Gemini (Antigravity代理)
- **API地址**: `http://127.0.0.1:8045/v1`
- **API密钥**: `sk-985786ae787d43e6b8d42688f39ed83a`
- **模型名称**: `gemini-3-pro-high`
- **温度参数**: 0.7
- **最大令牌数**: 4000

### 使用方法

1. **启动AutoGLM应用**
   ```bash
   ./venv/bin/python gui_main.py
   ```

2. **进入模型服务页面**
   - 在主界面点击"模型服务"
   - 在服务列表中找到"Gemini (Antigravity代理)"
   - 点击"激活"按钮设置为当前服务

3. **测试连接**
   - 选中Gemini服务
   - 点击"测试连接"按钮
   - 确认显示"连接成功"

## API调用方式

### 1. 直接Gemini API调用

```python
import google.generativeai as genai

# 使用 Antigravity 代理地址
genai.configure(
    api_key="sk-985786ae787d43e6b8d42688f39ed83a",
    transport='rest',
    client_options={'api_endpoint': 'http://127.0.0.1:8045'}
)

model = genai.GenerativeModel('gemini-3-pro-high')
response = model.generate_content("Hello")
print(response.text)
```

### 2. OpenAI兼容接口

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8045/v1",
    api_key="sk-985786ae787d43e6b8d42688f39ed83a"
)

response = client.chat.completions.create(
    model="gemini-3-pro-high",
    messages=[
        {"role": "user", "content": "Hello, 请介绍一下你自己"}
    ],
    max_tokens=500,
    temperature=0.7
)

print(response.choices[0].message.content)
```

## 模型特性

### Gemini-3-Pro-High

- **多模态支持**: 支持文本、图像、音频等多种输入
- **推理能力强**: 在复杂推理和问题解决方面表现出色
- **代码生成**: 支持多种编程语言的代码生成和解释
- **多语言支持**: 支持包括中文在内的多种语言
- **上下文理解**: 具有强大的长文本理解和生成能力

## 适用场景

### 推荐使用Gemini的场景：

1. **复杂任务分析**: 需要深度推理的任务
2. **代码相关任务**: 编程、调试、代码解释
3. **多步骤操作**: 需要分解复杂操作的任务
4. **创意内容**: 需要创造性思维的任务
5. **多语言处理**: 涉及多种语言的场景

### 参数建议

- **温度参数**: 0.7 (平衡创造性和准确性)
- **最大令牌数**: 4000 (支持长文本生成)
- **超时设置**: 30秒 (Gemini响应时间较长)

## 测试验证

运行测试脚本验证配置：

```bash
./venv/bin/python test_gemini_config.py
```

测试内容包括：
- ✅ 直接Gemini API调用
- ✅ OpenAI兼容接口调用  
- ✅ 模型服务配置验证

## 故障排除

### 常见问题

1. **连接超时**
   - 检查网络连接
   - 确认代理服务运行正常
   - 增加超时时间设置

2. **模型不存在错误**
   - 确认模型名称正确：`gemini-3-pro-high`
   - 检查API地址：`http://127.0.0.1:8045/v1`

3. **响应为空**
   - 检查API密钥是否正确
   - 确认请求参数格式正确
   - 尝试简化测试内容

### 调试方法

1. **查看日志**
   - 应用日志会记录API调用详情
   - 检查错误信息和响应状态

2. **手动测试**
   - 使用curl命令直接测试API
   - 验证网络连通性

3. **配置检查**
   - 确认所有参数填写正确
   - 验证服务激活状态

## 性能优化

### 建议设置

- **并发请求**: 避免同时发送多个请求
- **缓存结果**: 对重复查询进行缓存
- **分批处理**: 长文本任务分批处理

### 监控指标

- **响应时间**: 正常范围5-15秒
- **成功率**: 目标>95%
- **错误率**: 目标<5%

## 安全注意事项

1. **API密钥保护**: 不要在代码中硬编码密钥
2. **网络安全**: 确保代理服务安全配置
3. **数据隐私**: 注意敏感数据处理
4. **访问控制**: 限制API访问权限

## 更新日志

- **2025-01-07**: 添加Gemini API支持
- **2025-01-07**: 集成Antigravity代理配置
- **2025-01-07**: 完成测试验证

## 技术支持

如遇到问题，请：

1. 查看应用日志文件
2. 运行测试脚本诊断
3. 检查网络和代理状态
4. 联系技术支持团队
