from typing import Optional, Dict, Any,List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .agent_state import Task
import os
import yaml
from .agent_nodes import WrokflowNodes
from langchain_deepseek import ChatDeepSeek
from ..tools import Email_tool,SchedulerTask_tool,ContactTool
from langgraph.prebuilt import ToolNode
from ..service.receive_emails_service import EmailMessage

class EmailAgent:
    """Email Agent主类"""

    def __init__(self, config_path: Optional[str] = None):
        """初始化Agent
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认配置
        """

        # 加载配置
        self.config: Dict[str, Any] = self._load_config(config_path)
        
        # 初始化llm
        self.llm = ChatDeepSeek(
            model=self.config['model'],
            api_key=self.config['api_key']
        )

        # 初始化工具
        send_email_tool = Email_tool.send_email_simple
        add_daily_task_tool = SchedulerTask_tool.add_daily_task
        add_oneTime_task_tool = SchedulerTask_tool.add_oneTime_task
        get_all_task_tool = SchedulerTask_tool.get_all_task
        search_contact = ContactTool.search_contact
        add_contact = ContactTool.add_contact

        self.tools = [
            send_email_tool,
            add_daily_task_tool,
            add_oneTime_task_tool,
            get_all_task_tool,
            add_contact,
            search_contact
            ]

        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # 初始化节点
        self.nodes = WrokflowNodes(self.llm_with_tools)

        #memory 检查点
        self.memory = MemorySaver()

        # 编译图
        self.compiled_workflow = self.build_workflow()

    def _load_config(self,config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件

        Args:
            config_path: 配置文件路径，如果为None则使用项目根目录下的config.yaml

        Returns:
            Dict[str, Any]: 包含llm配置的字典
        """
        if config_path is None:
            # 默认使用项目根目录下的config.yaml
            config_path = os.path.join(os.path.dirname(__file__), "../../../config.yaml")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件未找到: {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件解析失败: {e}")

        # 提取llm配置
        if 'llm' not in config_data:
            raise ValueError("配置文件中缺少 'llm' 部分")

        llm_config = config_data['llm']

        # 验证必需的配置项
        required_keys = ['model', 'api_key']
        for key in required_keys:
            if key not in llm_config:
                raise ValueError(f"llm配置中缺少必需的键: {key}")

        # 返回字典对象
        return llm_config 


        

    def build_workflow(self) -> StateGraph:
        # 创建状态图
        workflow = StateGraph(Task)

        # 添加节点
        workflow.add_node("process_email",self.nodes.process_email)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.add_node("send_email",self.nodes.send_email)
        workflow.add_node("mark_as_replied", self.nodes.mark_as_replied)

        # 设置工作流
        workflow.set_entry_point("process_email")

        # 自定义路由函数：根据状态决定下一步
        def route_after_process(state: Task) -> str:
            """自定义路由函数，处理 process_email 节点之后的流程"""
            # 检查是否已经回复（通过工具发送了邮件）
            email_replied = state.get("email_replied", False)
            if email_replied:
                # 邮件已发送，直接标记为已处理
                return "mark_as_replied"

            # 检查状态
            status = state.get("status", "")

            # 如果状态为 ignored，直接跳转到 mark_as_replied
            if status == "ignored":
                return "mark_as_replied"

            # 检查是否有工具调用
            messages = state.get("messages", [])
            if messages and len(messages) > 0:
                last_message = messages[-1]
                if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                    return "tools"

            # 其他情况：需要发送邮件
            return "send_email"

        # process_email 节点：使用自定义路由函数
        workflow.add_conditional_edges(
            "process_email",
            route_after_process,
            {
                "tools": "tools",
                "send_email": "send_email",
                "mark_as_replied": "mark_as_replied"
            }
        )

        # tools 节点执行完后，返回 process_email，让 agent 继续决定是否需要调用更多工具
        workflow.add_edge("tools", "process_email")

        # ⚠️ 注意：不能添加 process_email -> send_email 的无条件边
        # 因为这会与条件边冲突，导致即使邮件已处理完成也会错误地进入 send_email 节点
        # 正确的流程由条件边控制：tools 返回 "end" 时 -> send_email

        # 发送邮件成功后，进入标记邮件节点
        workflow.add_edge("send_email","mark_as_replied")

        # mark_as_replied 节点执行完后，结束流程
        workflow.add_edge("mark_as_replied", END)

        # 编译工作流并返回可执行图（支持检查点）
        return workflow.compile(checkpointer=self.memory)
    
    def run(self,email_message:EmailMessage) -> Dict[str,Any]:
        """运行Agent处理email

        Args:
            email_message: 邮件内容（EmailMessage类实例）

        Returns:
            处理结果字典
        """

        # 将EmailMessage类实例转换为字典
        email_dict = email_message.to_dict() if hasattr(email_message, 'to_dict') else email_message

        # 创建初始状态
        initial_state = {
            "email_message": email_dict,
            "email_replied": False,  # 初始化为未回复状态
        }

        try:
            #运行工作流
            final_state = self.compiled_workflow.invoke(
                initial_state,
                {
                    "configurable": {"thread_id": "1"},
                    "recursion_limit": 1000
                }
            )

            result = {
                "success":True,
                "messages":"邮件已经被agent处理",
                "result":final_state.get("status", "unknown"),
            }

            print(result)
            return result
        except Exception as e:
            errors = {
                "success": False,
                "messages":f"邮件处理错误：{str(e)}",
            }
            print(f"email_agent错误：{errors}")
            return errors

    