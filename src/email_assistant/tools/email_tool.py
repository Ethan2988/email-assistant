from ..service import QQEmailService
from typing import List, Dict, Any, Optional, Union
from langchain.tools import tool
import logging
logger = logging.getLogger(__name__)

email_service = QQEmailService()

class Email_tool():
    
    @staticmethod
    @tool
    def send_email_simple(
        to_emails: Union[str, List[str]],
        subject: str,
        content: str,
        content_type: str = 'plain',
        cc_emails: Union[str, List[str]] = None,
        bcc_emails: Union[str, List[str]] = None,
        sender_name: Optional[str] = None,

        ) -> Dict[str,Any]:
        """
        发送简单邮件工具 - 用于向指定收件人发送邮件内容

        【使用场景】
        - 需要向用户发送邮件回复、通知或报告
        - 需要向多个收件人批量发送相同内容
        - 需要抄送或密送给其他人员

        【必填参数】
        - to_emails: 收件人邮箱地址
          * 类型：字符串或字符串列表
          * 单个收件人：'user@example.com'
          * 多个收件人：['user1@example.com', 'user2@example.com']
          * 注意：邮箱地址必须格式正确，否则会发送失败

        - subject: 邮件主题
          * 类型：字符串
          * 建议：简明扼要地描述邮件内容，避免空主题
          * 示例：'关于项目进度的汇报', '您询问的问题答复'

        - content: 邮件正文内容
          * 类型：字符串
          * 可以是纯文本或 HTML 内容（由 content_type 决定）
          * 建议：内容清晰、结构化，避免过于冗长

        【可选参数】
        - content_type: 内容类型，默认 'plain'
          * 'plain': 纯文本格式（推荐用于简单文本）
          * 'html': HTML 格式（推荐用于富文本、排版）

        - cc_emails: 抄送邮箱地址
          * 类型：字符串或字符串列表，默认 None
          * 用途：抄送给需要知悉邮件内容的人员
          * 示例：'cc@example.com' 或 ['cc1@example.com', 'cc2@example.com']

        - bcc_emails: 密送邮箱地址
          * 类型：字符串或字符串列表，默认 None
          * 用途：密送给需要隐藏收件的人员
          * 示例：'bcc@example.com'

        - sender_name: 发件人显示名称
          * 类型：字符串，默认 None
          * 如果不提供，将使用邮箱账号的默认名称
          * 示例：'Email Assistant', 'AI 助手'

        【返回值】
        返回字典包含以下字段：
        - success (bool): 是否发送成功
          * True: 发送成功
          * False: 发送失败

        - message (str): 发送结果消息
          * 成功：'发送邮件成功'
          * 失败：具体的错误原因

        - email_subject (str): 发送的邮件主题（用于确认）

        【使用示例】
        示例1 - 发送给单个收件人：
        send_email_simple(
            to_emails='user@example.com',
            subject='会议提醒',
            content='您好，明天下午3点有项目会议，请准时参加。'
        )

        示例2 - 发送给多个收件人并抄送：
        send_email_simple(
            to_emails=['user1@example.com', 'user2@example.com'],
            subject='项目周报',
            content='本周项目进度：已完成需求分析和原型设计。',
            cc_emails='manager@example.com',
            sender_name='AI 助手'
        )

        示例3 - 发送 HTML 邮件：
        send_email_simple(
            to_emails='user@example.com',
            subject='产品通知',
            content='<h1>欢迎使用我们的产品</h1><p>感谢您的注册！</p>',
            content_type='html'
        )

        【注意事项】
        1. 本工具不支持发送附件
        2. 邮箱地址必须有效且格式正确
        3. 发件人使用系统配置的邮箱账号（QQ邮箱）
        4. 发送失败会返回详细错误信息，请根据错误信息处理
        5. 建议在发送前验证收件人邮箱地址的正确性

        """
        try:
            logger.info(f"开始发送邮件: {subject}")
            print(f"开始发送邮件: {subject}")

            send_email_result = email_service.send_email(
                to_emails=to_emails,
                subject=subject,
                content=content,
                content_type=content_type,
                cc_emails=cc_emails,
                bcc_emails=bcc_emails,
                attachment_paths=None,
                reply_to=None,
                sender_name=sender_name,
            )

            if send_email_result["success"]:
                return {
                    'success':True,
                    'message':"发送邮件成功",
                    'email_subject':send_email_result["subject"]
                }
            else:
                return {
                    'success':False,
                    'message':send_email_result['message'],
                    'email_subject':f"{subject}"
                }
                
        except Exception as e:
            logger.error(f"邮件发送失败: {str(e)}")
            print(f"邮件发送失败: {str(e)}")
            return {
                'success': False,
                'message': f'邮件发送失败，异常：{str(e)}'
            }
