"""
状态模式定义 - 定义LangGraph工作流的状态结构
"""

import subprocess
import os
import re
from typing import List, Optional, Dict, Any, TypedDict, Annotated
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages



class EmailMessage(TypedDict):
    """接收邮件"""
    message_id:str
    subject: str
    from_email: str
    from_name: str
    to_email: str
    date: str
    body: str
    body_type: str  # 'plain' or 'html'
    cc: List[str]
    bcc: List[str]
    attachments: List[str]
    raw_email: str


class Task(TypedDict):
    """任务状态"""
    messages: Annotated[List, add_messages]
    status: str  # 'success', 'failed', 'Ignore'
    email_message: EmailMessage
    error: str
    email_replied: bool  # 邮件是否已回复，防止重复发送
    subject:str #发送邮件主题



    


