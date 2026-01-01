"""
LangGraph邮件发送工具
提供适合LangGraph调用的邮件发送功能
"""

import json
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import logging

try:
    from langchain_core.tools import BaseTool
    from pydantic import BaseModel, Field, validator
    from langchain_core.callbacks import CallbackManagerForToolRun
except ImportError:
    # 如果没有安装langchain，提供基础类定义
    class BaseTool:
        pass

    class BaseModel:
        pass

    def Field(default=None, description=None, **kwargs):
        return default

from ..service.send_email_service import QQEmailService

logger = logging.getLogger(__name__)


class SendEmailInput(BaseModel):
    """发送邮件的输入参数模型"""

    recipients: Union[str, List[str]] = Field(
        description="邮件收件人邮箱地址，可以是单个邮箱或邮箱列表"
    )
    subject: str = Field(
        description="邮件主题，清晰描述邮件内容"
    )
    content: str = Field(
        description="邮件正文内容，支持纯文本或HTML格式"
    )
    content_type: str = Field(
        default="plain",
        description="邮件内容类型，'plain'表示纯文本，'html'表示HTML格式"
    )
    cc_recipients: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="抄送收件人邮箱地址，可选"
    )
    bcc_recipients: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="密送收件人邮箱地址，可选"
    )
    attachments: Optional[List[str]] = Field(
        default=None,
        description="附件文件路径列表，可选"
    )
    sender_name: Optional[str] = Field(
        default=None,
        description="发件人显示名称，可选"
    )
    reply_to: Optional[str] = Field(
        default=None,
        description="回复邮箱地址，可选"
    )

    @validator('content_type')
    def validate_content_type(cls, v):
        if v not in ['plain', 'html']:
            raise ValueError("content_type必须是'plain'或'html'")
        return v

    @validator('recipients')
    def validate_recipients(cls, v):
        if isinstance(v, str):
            return [v]
        return v

    @validator('cc_recipients')
    def validate_cc_recipients(cls, v):
        if isinstance(v, str):
            return [v]
        return v

    @validator('bcc_recipients')
    def validate_bcc_recipients(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class SendEmailTool(BaseTool):
    """
    LangGraph邮件发送工具

    用于通过QQ邮箱发送邮件，支持文本、HTML格式、附件等功能。
    """

    name: str = "send_email"
    description: str = """
    发送邮件工具，用于通过QQ邮箱发送邮件。

    功能包括：
    - 发送纯文本或HTML格式邮件
    - 支持多个收件人、抄送、密送
    - 支持添加附件
    - 完善的错误处理和状态反馈

    使用场景：
    - 发送通知邮件
    - 发送报告文档
    - 发送营销邮件
    - 自动化邮件流程
    """

    args_schema: type = type("SendEmailInput", (SendEmailInput,), {})
    email_service: Any = None

    def __init__(self, **kwargs):
        """初始化邮件工具"""
        super().__init__(**kwargs)
        self.email_service = QQEmailService()

    def _run(
        self,
        recipients: Union[str, List[str]],
        subject: str,
        content: str,
        content_type: str = "plain",
        cc_recipients: Optional[Union[str, List[str]]] = None,
        bcc_recipients: Optional[Union[str, List[str]]] = None,
        attachments: Optional[List[str]] = None,
        sender_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """
        执行邮件发送操作

        Args:
            recipients: 收件人邮箱
            subject: 邮件主题
            content: 邮件内容
            content_type: 内容类型
            cc_recipients: 抄送收件人
            bcc_recipients: 密送收件人
            attachments: 附件列表
            sender_name: 发件人名称
            reply_to: 回复邮箱
            run_manager: 回调管理器

        Returns:
            str: JSON格式的发送结果
        """

        try:
            # 记录操作开始
            logger.info(f"开始发送邮件: {subject}")
            if run_manager:
                run_manager.on_tool_start({"recipients": recipients, "subject": subject})

            # 验证附件文件是否存在
            if attachments:
                missing_files = []
                for attachment in attachments:
                    if not Path(attachment).exists():
                        missing_files.append(attachment)

                if missing_files:
                    error_msg = f"附件文件不存在: {', '.join(missing_files)}"
                    logger.error(error_msg)
                    return self._format_error_result("FILE_ERROR", error_msg)

            # 发送邮件
            result = self.email_service.send_email(
                to_emails=recipients,
                subject=subject,
                content=content,
                content_type=content_type,
                cc_emails=cc_recipients,
                bcc_emails=bcc_recipients,
                attachment_paths=attachments,
                sender_name=sender_name,
                reply_to=reply_to
            )

            # 格式化结果
            if result['success']:
                success_msg = f"邮件发送成功: {subject}"
                logger.info(success_msg)
                if run_manager:
                    run_manager.on_tool_end({"status": "success", "message_id": result.get('message_id')})
                return self._format_success_result(result)
            else:
                error_msg = f"邮件发送失败: {result['message']}"
                logger.error(error_msg)
                if run_manager:
                    run_manager.on_tool_error(error_msg)
                return self._format_error_result(result.get('error_type', 'UNKNOWN_ERROR'), result['message'])

        except Exception as e:
            error_msg = f"邮件发送过程中发生异常: {str(e)}"
            logger.error(error_msg)
            if run_manager:
                run_manager.on_tool_error(error_msg)
            return self._format_error_result("EXCEPTION", error_msg)

    def _arun(self, *args, **kwargs):
        """异步运行（暂不支持）"""
        raise NotImplementedError("该工具不支持异步操作")

    def _format_success_result(self, result: Dict[str, Any]) -> str:
        """格式化成功结果"""
        return json.dumps({
            "success": True,
            "message": "邮件发送成功",
            "data": {
                "message_id": result.get('message_id'),
                "recipients": result.get('recipients', []),
                "subject": result.get('subject'),
                "timestamp": result.get('timestamp', '')  # 如果邮件服务返回时间戳
            }
        }, ensure_ascii=False, indent=2)

    def _format_error_result(self, error_type: str, message: str) -> str:
        """格式化错误结果"""
        return json.dumps({
            "success": False,
            "error_type": error_type,
            "message": message,
            "data": None
        }, ensure_ascii=False, indent=2)


class TestEmailConnectionTool(BaseTool):
    """
    测试邮件连接工具
    用于测试邮件服务配置是否正确
    """

    name: str = "test_email_connection"
    description: str = """
    测试邮件服务连接是否正常。

    使用场景：
    - 验证邮件配置是否正确
    - 检查网络连接状态
    - 诊断邮件发送问题
    """

    email_service: Any = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email_service = QQEmailService()

    def _run(self, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        """测试邮件连接"""
        try:
            logger.info("开始测试邮件连接...")
            if run_manager:
                run_manager.on_tool_start({"action": "test_connection"})

            result = self.email_service.test_connection()

            if result['success']:
                success_msg = "邮件连接测试成功"
                logger.info(success_msg)
                if run_manager:
                    run_manager.on_tool_end({"status": "connected"})
                return json.dumps({
                    "success": True,
                    "message": success_msg,
                    "data": {
                        "smtp_server": result.get('smtp_server'),
                        "sender_email": result.get('sender_email')
                    }
                }, ensure_ascii=False, indent=2)
            else:
                error_msg = f"邮件连接测试失败: {result['message']}"
                logger.error(error_msg)
                if run_manager:
                    run_manager.on_tool_error(error_msg)
                return json.dumps({
                    "success": False,
                    "error_type": "CONNECTION_ERROR",
                    "message": error_msg,
                    "data": None
                }, ensure_ascii=False, indent=2)

        except Exception as e:
            error_msg = f"连接测试过程中发生异常: {str(e)}"
            logger.error(error_msg)
            if run_manager:
                run_manager.on_tool_error(error_msg)
            return json.dumps({
                "success": False,
                "error_type": "EXCEPTION",
                "message": error_msg,
                "data": None
            }, ensure_ascii=False, indent=2)

    def _arun(self, *args, **kwargs):
        """异步运行（暂不支持）"""
        raise NotImplementedError("该工具不支持异步操作")


class EmailConfigTool(BaseTool):
    """
    邮件配置工具
    获取当前邮件服务配置信息
    """

    name: str = "get_email_config"
    description: str = """
    获取当前邮件服务配置信息。

    使用场景：
    - 查看邮件配置状态
    - 验证配置是否完整
    - 获取发件人信息
    """

    email_service: Any = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email_service = QQEmailService()

    def _run(self, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        """获取邮件配置"""
        try:
            logger.info("获取邮件配置信息...")
            if run_manager:
                run_manager.on_tool_start({"action": "get_config"})

            config_summary = self.email_service.email_config.get_config_summary()

            # 隐藏敏感信息
            safe_config = {
                "smtp_server": config_summary.get('smtp_server'),
                "smtp_port": config_summary.get('smtp_port'),
                "sender_email": config_summary.get('sender_email'),
                "sender_name": config_summary.get('sender_name'),
                "test_mode": config_summary.get('test_mode'),
                "config_valid": config_summary.get('config_valid'),
                "auth_code_configured": config_summary.get('auth_code_configured')
            }

            success_msg = "邮件配置获取成功"
            logger.info(success_msg)
            if run_manager:
                run_manager.on_tool_end({"config_valid": safe_config['config_valid']})

            return json.dumps({
                "success": True,
                "message": success_msg,
                "data": safe_config
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            error_msg = f"获取邮件配置时发生异常: {str(e)}"
            logger.error(error_msg)
            if run_manager:
                run_manager.on_tool_error(error_msg)
            return json.dumps({
                "success": False,
                "error_type": "EXCEPTION",
                "message": error_msg,
                "data": None
            }, ensure_ascii=False, indent=2)

    def _arun(self, *args, **kwargs):
        """异步运行（暂不支持）"""
        raise NotImplementedError("该工具不支持异步操作")


# 创建工具实例，方便直接导入使用
send_email_tool = SendEmailTool()
test_email_connection_tool = TestEmailConnectionTool()
email_config_tool = EmailConfigTool()

# 工具集合，方便在LangGraph中使用
EMAIL_TOOLS = [
    send_email_tool,
    test_email_connection_tool,
    email_config_tool
]


if __name__ == "__main__":
    # 测试代码
    print("=== 测试邮件配置工具 ===")
    config_result = email_config_tool._run()
    print(config_result)

    print("\n=== 测试邮件连接工具 ===")
    connection_result = test_email_connection_tool._run()
    print(connection_result)

    print("\n=== 测试邮件发送工具 ===")
    # 注意：这会尝试发送真实邮件，请谨慎测试
    # email_result = send_email_tool._run(
    #     recipients="test@example.com",
    #     subject="测试邮件",
    #     content="这是一封测试邮件"
    # )
    # print(email_result)
    print("邮件发送工具已就绪（跳过实际发送测试）")