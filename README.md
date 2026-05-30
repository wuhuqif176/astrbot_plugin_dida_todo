# 滴答清单待办插件 for AstrBot

将滴答清单（TickTick / 滴答清单）无缝集成到 AstrBot 中，支持**自然语言创建任务**和**查询待办**。  
利用 AstrBot 的 Function Calling 能力，你只需像对人说话一样：“明天下午3点提醒我开会”，即可自动创建带截止时间的任务。

## ✨ 功能特性

- ✅ 自然语言解析：自动识别“明天、后天、下午3点”等时间描述
- ✅ 创建任务：一句话添加待办，自动关联默认项目（优先“任务”项目）
- ✅ 查询任务：列出所有未完成的任务及其ID和截止日期
- ✅ 指令备用：同时支持 `/todo list` 和 `/todo add <标题> [时间]` 命令
- ✅ 完全兼容 AstrBot 的 Function Calling 智能体模式

### 获取 Token
    登录滴答清单
    点击你的头像 → 设置 → 账号与安全 → API口令

## ⚙️ 配置

在 AstrBot 配置界面（或 `data/cmd_config.json`）中设置：

```json
{
  "dida_token": "你的_API_Token"
}