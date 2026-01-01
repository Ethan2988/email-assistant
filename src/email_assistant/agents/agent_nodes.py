from typing import Dict, Any, List, Tuple
from datetime import datetime
import time
import os
from langgraph.graph import StateGraph, END
from .agent_state import Task,EmailMessage
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import AIMessage
from ..config import EmailConfig
from ..service import QQEmailService

class WrokflowNodes:
    """工作流节点实现类"""
    def __init__(self,llm:ChatDeepSeek):
        """初始化节点"""
        # 加载llm
        self.llm = llm
        # master_email,agent 接收该邮箱的指令
        self.master_email = EmailConfig().get_master_info().get('master_email')
        self.assistant_email = EmailConfig().get_imap_config()['email']
        self.send_email_service = QQEmailService()

    
    # 阅读邮件节点
    def process_email(self,state:Task) -> Dict[str,Any]:
        """
        接收到邮件，进行处理节点
        :return: 说明
        :rtype: Dict[str, Any]
        """
        email_message = state.get("email_message", {})

        if not email_message:
            return {"email_message": {}}

        # ⭐ 检查邮件是否已经被回复过（防止重复发送）
        email_replied = state.get("email_replied", False)
        if email_replied:
            print(f"✅ 邮件已处理过，跳过重复处理: {email_message.get('subject', '')}")
            return {
                "status": "email_proccessed",
                "messages": "Email already replied, skipping duplicate processing"
            }

        # ⭐ 检查是否有工具执行结果，如果有且是 email_tool，则标记为已回复
        messages = state.get("messages", [])

        # 检查最后一条消息是否是工具调用结果，且来自 email_tool
        if messages and len(messages) > 0:
            last_message = messages[-1]
            # 如果最后一条消息是 ToolMessage，说明刚执行完工具
            if hasattr(last_message, 'name') and last_message.name == 'send_email_simple':
                print(f"✅ 检测到邮件已发送，标记为已处理")
                return {
                    "messages": [AIMessage(content="邮件已发送，任务完成")],
                    "status": "success",
                    "email_replied": True  # 标记为已回复
                }

        try:
            
            # ⭐ 忽略自己发送的邮件
            if email_message.get("from_email") == self.assistant_email:
                print(f"⚠️ Agent 跳过自己发送的邮件: {email_message.get('subject', '')}")
                return {
                    "status": "ignored",
                    "messages": "Ignore email : Self-sent email",
                    "email_replied": False,  # 尚未回复，等待工具调用
                }

            if email_message.get("from_email") == self.master_email:
                # 获取历史消息
                history_messages = state.get("messages", [])

                # 如果是第一次处理（没有历史消息），添加初始邮件内容
                if len(history_messages) == 0:
                    # 格式化邮件内容为可读文本
                    email_content = f"""
                    主题: {email_message.get('subject', '')}
                    发件人: {email_message.get('from_name', '')} <{email_message.get('from_email', '')}>
                    日期: {email_message.get('date', '')}
                    正文:
                    {email_message.get('body', '')}
                    """

                    # # 创建系统提示词
                    # system_prompt = f"""
                    #     你是一个精通使用各种工具的邮箱助理：Email Assistant
                    #     你会接收到用户的邮件，如果邮件的发件人为：{self.master_email}，则请以一个邮箱助理的身份按照如下规则进行处理：
                    #     - 如果用户的邮件内容是正常咨询、询问、要求翻译、回信等，代替用户发送邮件等任务，则请按照用户的诉求进行回答，并调用 email_tool 发送邮件，告知用户你的回答
                    #     - 如果用户要求创建定时任务进行提醒，则可以调用 add_daily_task_tool，创建定时任务，不论系统返回是否创建成功，调用 email_tool 发送邮件告知客户结果
                    #     - 如果用户要求查询有哪些定时任务进，则可以调用 get_all_task_tool，创建定时任务，不论系统返回查询是否成功，调用 email_tool 发送邮件告知客户结果
                    #     - 完成任务后，最终是向{self.master_email}回复邮件告知执行结果
                    # """

                    system_prompt = f"""
                        你是一个精通使用各种工具的邮箱助理：Email Assistant
                        你会接收到用户的邮件，如果邮件的发件人为：{self.master_email}，这是系统中的master用户，用来通过邮件来发送指令或请求，则请以一个邮箱助理的身份按照如下规则进行处理：
                        - 如果master用户的邮件内容是正常咨询、询问、要求翻译、回信等，代替用户发送邮件等任务，则请按照用户的诉求进行回答，回答内容请作为一封正式邮件的内容
                        - 如果master用户要求代发邮件，则可以调用 send_email_tool 这个工具来发送邮件，如果master没有给具体的发送的email地址，则可以调用search_contact 工具查询联系人，找到地址，如果也查询不到，则回复一封咨询油价给master用户，询问email地址
                        - 如果用户要求创建定时任务进行提醒，则可以调用 add_daily_task_tool，创建定时任务，不论系统返回是否创建成功，都要回答任务执行的结果，并形成一封正式邮件的内容
                        - 如果用户要求查询有哪些定时任务进，则可以调用 get_all_task_tool，创建定时任务，不论系统返回查询是否成功，都要回答任务执行的结果，并形成一封正式邮件的内容
                        - 完成任务后，你最终是向{self.master_email}回复邮件告知执行结果，所以回答的内容要正式、有温度，以一个助理的身份回答
                    """

                    # 构建初始消息列表
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": email_content}
                    ]
                else:
                    # 如果有历史消息，直接使用（LangGraph 的 add_messages 会自动累积）
                    messages = history_messages

                # 调用 LLM（使用绑定工具的 llm_with_tools）
                res = self.llm.invoke(messages)


                return {
                    "messages": [res],
                    "status": "agent_replied",
                    "email_replied": False,  # 尚未回复，等待工具调用,
                    "subject":f"回复:{email_message.get('subject', 'Agent回复邮件')}"
                }
            else:
                return {
                    "status": "ignored",
                    "messages": "It's not master's email, No need to reply to the email.",
                    "email_replied": False
                }
        except Exception as e:
            return {
                    "status": "agent_processed_failed",
                    "error": str(e),
                    "subject":"Agent process email error",
                    "messages":f"Sorry , Agent process email error, detail as below: {str(e)},please try again later!",
                    "email_replied": False
                }

    
    # 发送邮件节点
    def send_email(self,state:Task) -> Dict[str,Any]:
        """
        发送邮件的节点，用于发送邮件
        param:
            state:Task

        return: 返回发送邮件结果,类型，Dict[str, Any]
        """

        try:
            to_email = self.master_email
            subject = state.get("subject")

            # 从 messages 列表中提取最后一条 AIMessage 的 content
            messages = state.get("messages", [])
            content = ""
            if messages:
                # 找到最后一条 AIMessage
                for msg in reversed(messages):
                    if hasattr(msg, 'content') and isinstance(msg, AIMessage):
                        content = msg.content
                        break

            # 如果没有找到 content，使用默认值
            if not content:
                content = "Agent没有正确返回内容～"

            send_email_result = self.send_email_service.send_simple_email(
                to_email=to_email,
                subject=subject,
                content = content
            )

            if send_email_result["success"]:
                #邮件发送成功
                return {
                    "status":"send_email_success",
                    "messages":"Email has been send",
                    "email_replied": False,
                    "email_subject":subject
                }
            else:
                #邮件发送失败
                return {
                    "status":"send_email_failed",
                    "messages":"Email send error",
                    "email_replied": False,
                    "error": send_email_result["message"]
                }

        except Exception as e:
            return {
                    "status":"send_email_failed",
                    "messages":"Email send exception error",
                    "email_replied": False,
                    "error": f"{str(e)}"
                }




    #标记邮件已处理节点
    def mark_as_replied(self, state:Task) -> Dict[str,Any]:
        """
        标记邮件已处理，防止重复发送
        :param state: 当前状态
        :return: 更新后的状态
        """
        print(f"📧 邮件回复已完成，标记为已处理")
        return {
            "email_replied": True,
            "status": "email_proccessed"
        }



