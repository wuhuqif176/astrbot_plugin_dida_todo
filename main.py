# main.py
# 滴答清单插件 v1.0.1 - 修复配置读取报错，支持UI配置Token

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

# 引入官方 Function Calling 核心组件
from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

import httpx
import re
from datetime import datetime, timedelta

# ================= 全局变量与常量 =================
PLUGIN_CONFIG = {}  # 用于存储插件配置的全局字典
BASE_URL = "https://api.dida365.com/open/v1"


# ================================================

def get_headers(token: str):
    """生成请求头"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


async def get_default_project_id(token: str):
    """获取默认项目ID"""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/project", headers=get_headers(token))
            resp.raise_for_status()
            projects = resp.json()
            if not projects:
                return None
            for p in projects:
                if p.get('name') == '任务':
                    return p.get('id')
            return projects[0].get('id')
        except Exception as e:
            logger.error(f"获取项目列表失败: {e}")
            return None


def parse_time(natural: str):
    """解析自然语言时间为 ISO 格式"""
    if not natural: return None
    natural = natural.lower()
    match = re.search(r'(明天|后天)?\s*(下午|晚上|上午|早上)?\s*(\d{1,2})(?::(\d{2}))?点?', natural)
    if not match: return None

    day_offset = 1 if match.group(1) == '明天' else (2 if match.group(1) == '后天' else 0)
    period = match.group(2) or ''
    hour = int(match.group(3))
    minute = int(match.group(4)) if match.group(4) else 0

    if period in ['下午', '晚上'] and hour != 12:
        hour += 12
    elif period in ['上午', '早上'] and hour == 12:
        hour = 0

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day_offset > 0:
        target += timedelta(days=day_offset)
    elif target <= now:
        target += timedelta(days=1)

    return target.isoformat(timespec='seconds') + '+08:00'


# ============== 核心异步业务函数 ==============

async def do_create_task(token: str, title: str, due_date: str = None):
    """创建新任务"""
    project_id = await get_default_project_id(token)
    if not project_id:
        return "❌ 未找到滴答清单项目，请检查授权或网络连接。"

    async with httpx.AsyncClient() as client:
        try:
            payload = {"title": title, "projectId": project_id}
            if due_date:
                payload["dueDate"] = due_date

            resp = await client.post(
                f"{BASE_URL}/task",
                headers=get_headers(token),
                json=payload,
                timeout=10.0
            )
            resp.raise_for_status()
            task = resp.json()
            msg = f"✅ 滴答清单任务已创建: {title} (ID: {task.get('id')})"
            if due_date:
                msg += f"\n⏰ 截止时间: {due_date}"
            return msg
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            return f"❌ 创建任务失败: {str(e)}"


async def do_get_all_tasks(token: str):
    """获取所有未完成任务"""
    tasks = []
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/project", headers=get_headers(token))
            resp.raise_for_status()
            for proj in resp.json():
                data_resp = await client.get(
                    f"{BASE_URL}/project/{proj['id']}/data",
                    headers=get_headers(token),
                    timeout=10.0
                )
                if data_resp.status_code == 200:
                    for t in data_resp.json().get('tasks', []):
                        if t.get('status') != 2:
                            t['id'] = str(t.get('id'))
                            tasks.append(t)
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
    return tasks


def format_task_list(tasks):
    """格式化任务列表"""
    if not tasks: return "🎉 所有任务都完成啦！"
    lines = ["📋 滴答清单待办列表:"]
    for i, t in enumerate(tasks, 1):
        due = t.get('dueDate', '')
        due_str = f" (截止: {due[:10]})" if due else ""
        lines.append(f"  {i}. [{t.get('id')}] {t.get('title')}{due_str}")
    return "\n".join(lines)


# ============== 🌟 官方标准：定义 Tools ==============

@dataclass
class CreateDidaTaskTool(FunctionTool[AstrAgentContext]):
    """添加任务到滴答清单"""
    name: str = "create_dida_task"
    description: str = "【重要】将任务添加到用户的【滴答清单(TickTick)】待办列表中。当用户说'帮我建个任务'、'添加到待办'、'记一下明天要开会'时，必须使用此工具！"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "任务标题，简洁描述要做什么，如'开会'、'买牛奶'。"},
                "time_description": {"type": "string",
                                     "description": "截止时间的自然语言描述，如'明天下午3点'。如果没有提到时间则留空字符串。"}
            },
            "required": ["title"]
        }
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        # 直接从全局变量读取配置
        token = PLUGIN_CONFIG.get("dida_token", "")
        if not token:
            return "❌ 请先在插件配置中设置滴答清单的 API Token。"

        title = kwargs.get("title", "")
        time_desc = kwargs.get("time_description", "")
        due = parse_time(time_desc) if time_desc else None
        return await do_create_task(token, title, due)


@dataclass
class ListDidaTasksTool(FunctionTool[AstrAgentContext]):
    """查询滴答清单任务"""
    name: str = "list_dida_tasks"
    description: str = "查询滴答清单(TickTick)中所有未完成的待办任务。当用户问'我有什么任务'、'查看待办'、'我的任务列表'时调用此工具。"
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        # 直接从全局变量读取配置
        token = PLUGIN_CONFIG.get("dida_token", "")
        if not token:
            return "❌ 请先在插件配置中设置滴答清单的 API Token。"

        tasks = await do_get_all_tasks(token)
        return format_task_list(tasks)


# ============== 插件主体 ==============
@register(
    "astrbot_plugin_dida_todo",
    "Your Name",
    "滴答清单待办管理（支持自然语言）",
    "1.0.1",
    "支持指令模式和自然语言模式管理滴答清单任务"
)
class DidaTodoPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 将配置保存到全局变量中，供 Tool 类调用
        global PLUGIN_CONFIG
        PLUGIN_CONFIG = config

        logger.info("滴答清单插件 v3.1.0 已加载 (已修复配置读取问题)")

        try:
            self.context.add_llm_tools(
                CreateDidaTaskTool(),
                ListDidaTasksTool()
            )
            logger.info("🎉 成功！滴答清单 Function Calling 工具已注册！")
        except Exception as e:
            logger.error(f"❌ 工具注册失败: {type(e).__name__}: {e}")

    # ========== 指令模式 (保留作为备用) ==========
    @filter.command("todo")
    async def todo_cmd(self, event: AstrMessageEvent):
        token = PLUGIN_CONFIG.get("dida_token", "")
        if not token:
            yield event.plain_result("❌ 请先在插件配置中设置滴答清单的 API Token。")
            return

        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result(
                "📋 用法：\n"
                "/todo list              - 查看所有待办任务\n"
                "/todo add <标题> [时间]  - 添加新任务\n\n"
                "💡 推荐直接用自然语言对话。"
            )
            return

        subcmd = args[1]
        if subcmd == "list":
            tasks = await do_get_all_tasks(token)
            yield event.plain_result(format_task_list(tasks))
        elif subcmd == "add":
            if len(args) < 3:
                yield event.plain_result("用法：/todo add <标题> [时间描述]")
                return
            title = args[2]
            time_desc = " ".join(args[3:]) if len(args) > 3 else None
            due = parse_time(time_desc) if time_desc else None
            msg = await do_create_task(token, title, due)
            yield event.plain_result(msg)
        else:
            yield event.plain_result(f"未知子命令: {subcmd}\n可用命令：list, add")