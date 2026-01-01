"""
QQ邮件发送服务
支持发送文本邮件、HTML邮件、附件，以及完善的错误处理
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
import chardet
from email_validator import validate_email, EmailNotValidError
from ..config import EmailConfig


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QQEmailService:
    """QQ邮件发送服务"""

    def __init__(self, config_path: str = None):
        """
        初始化邮件服务

        Args:
            config_path: 配置文件路径
        """
        self.email_config = EmailConfig(config_path)
        self.smtp_config = self.email_config.get_smtp_config()
        self.sender_info = self.email_config.get_sender_info()

    def _validate_email(self, email: str) -> bool:
        """验证邮箱地址格式"""
        try:
            # 只验证格式，不检查DNS可投递性
            validate_email(email, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False

    def _detect_file_encoding(self, file_path: str) -> str:
        """检测文件编码"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                result = chardet.detect(raw_data)
                return result['encoding'] or 'utf-8'
        except Exception:
            return 'utf-8'

    def _create_smtp_connection(self) -> smtplib.SMTP:
        """创建SMTP连接"""
        try:
            # 创建SMTP连接
            smtp = smtplib.SMTP(self.smtp_config['smtp_server'], self.smtp_config['smtp_port'])

            # 设置调试级别
            smtp.set_debuglevel(0)

            # 启用安全传输
            smtp.starttls()

            # 登录
            smtp.login(self.smtp_config['sender_email'], self.smtp_config['auth_code'])

            logger.info("SMTP连接建立成功")
            return smtp

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP认证失败，请检查邮箱地址和授权码")
            raise
        except smtplib.SMTPConnectError:
            logger.error("SMTP连接失败，请检查网络连接")
            raise
        except Exception as e:
            logger.error(f"创建SMTP连接时发生未知错误: {str(e)}")
            raise

    def _add_attachments(self, msg: MIMEMultipart, attachment_paths: List[str]) -> None:
        """添加附件到邮件"""
        for file_path in attachment_paths:
            try:
                path_obj = Path(file_path)
                if not path_obj.exists():
                    logger.error(f"附件文件不存在: {file_path}")
                    raise FileNotFoundError(f"附件文件不存在: {file_path}")

                # 检测文件编码
                encoding = self._detect_file_encoding(file_path)

                # 根据文件类型创建附件
                content_type = self._get_content_type(path_obj.suffix)

                with open(file_path, 'rb') as attachment:
                    part = MIMEBase(*content_type.split('/'))
                    part.set_payload(attachment.read())

                encoders.encode_base64(part)

                # 添加附件头
                filename = path_obj.name
                try:
                    # 尝试使用正确的文件名编码
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= "{filename}"'
                    )
                except UnicodeEncodeError:
                    # 如果编码失败，使用安全文件名
                    safe_filename = filename.encode('ascii', errors='ignore').decode('ascii')
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= "{safe_filename}"'
                    )

                msg.attach(part)
                logger.info(f"附件添加成功: {filename}")

            except Exception as e:
                logger.error(f"添加附件失败 {file_path}: {str(e)}")
                raise

    def _get_content_type(self, file_extension: str) -> str:
        """根据文件扩展名获取Content-Type"""
        extension = file_extension.lower()
        content_types = {
            '.txt': 'text/plain',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
        }
        return content_types.get(extension, 'application/octet-stream')

    def send_email(
        self,
        to_emails: Union[str, List[str]],
        subject: str,
        content: str,
        content_type: str = 'plain',
        cc_emails: Union[str, List[str]] = None,
        bcc_emails: Union[str, List[str]] = None,
        attachment_paths: List[str] = None,
        reply_to: str = None,
        sender_name: str = None
    ) -> Dict[str, Any]:
        """
        发送邮件

        Args:
            to_emails: 收件人邮箱，可以是单个邮箱或邮箱列表
            subject: 邮件主题
            content: 邮件内容
            content_type: 内容类型，'plain'或'html'
            cc_emails: 抄送邮箱
            bcc_emails: 密送邮箱
            attachment_paths: 附件路径列表
            reply_to: 回复邮箱
            sender_name: 发件人姓名

        Returns:
            Dict: 发送结果，包含success、message、message_id等字段
        """
        smtp = None
        try:
            # 参数验证和标准化
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            if isinstance(cc_emails, str):
                cc_emails = [cc_emails] if cc_emails else []
            if isinstance(bcc_emails, str):
                bcc_emails = [bcc_emails] if bcc_emails else []

            cc_emails = cc_emails or []
            bcc_emails = bcc_emails or []
            attachment_paths = attachment_paths or []

            # 验证邮箱格式
            all_emails = to_emails + cc_emails + bcc_emails
            for email in all_emails:
                if not self._validate_email(email):
                    raise ValueError(f"无效的邮箱地址: {email}")

            # 创建邮件消息
            msg = MIMEMultipart()
            msg['From'] = formataddr((sender_name or self.sender_info['name'], self.sender_info['email']))
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject

            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
            if reply_to:
                msg['Reply-To'] = reply_to

            # 添加邮件正文
            if content_type.lower() == 'html':
                msg.attach(MIMEText(content, 'html', 'utf-8'))
            else:
                msg.attach(MIMEText(content, 'plain', 'utf-8'))

            # 添加附件
            if attachment_paths:
                self._add_attachments(msg, attachment_paths)

            # 创建SMTP连接并发送
            smtp = self._create_smtp_connection()

            # 合并所有收件人
            all_recipients = to_emails + cc_emails + bcc_emails

            # 发送邮件
            result = smtp.send_message(msg, to_addrs=all_recipients)

            # QQ邮箱返回的格式是: {'ok': '1 Message accepted for delivery'}
            message_id = result.get('ok', '') if isinstance(result, dict) else str(result)

            logger.info(f"邮件发送成功，收件人: {', '.join(all_recipients)}")

            return {
                'success': True,
                'message': '邮件发送成功',
                'message_id': message_id,
                'recipients': all_recipients,
                'subject': subject
            }

        except ValueError as e:
            logger.error(f"参数验证失败: {str(e)}")
            return {
                'success': False,
                'message': f'参数验证失败: {str(e)}',
                'error_type': 'validation_error'
            }
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP认证失败: {str(e)}")
            return {
                'success': False,
                'message': 'SMTP认证失败，请检查邮箱配置',
                'error_type': 'auth_error'
            }
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"收件人被拒绝: {str(e)}")
            return {
                'success': False,
                'message': '收件人地址被拒绝',
                'error_type': 'recipient_error'
            }
        except smtplib.SMTPException as e:
            logger.error(f"SMTP错误: {str(e)}")
            return {
                'success': False,
                'message': f'SMTP错误: {str(e)}',
                'error_type': 'smtp_error'
            }
        except FileNotFoundError as e:
            logger.error(f"文件未找到: {str(e)}")
            return {
                'success': False,
                'message': f'附件文件未找到: {str(e)}',
                'error_type': 'file_error'
            }
        except Exception as e:
            logger.error(f"发送邮件时发生未知错误: {str(e)}")
            return {
                'success': False,
                'message': f'发送失败: {str(e)}',
                'error_type': 'unknown_error'
            }
        finally:
            if smtp:
                try:
                    smtp.quit()
                except Exception:
                    pass

    def send_simple_email(self, to_email: str, subject: str, content: str) -> Dict[str, Any]:
        """
        发送简单文本邮件的便捷方法

        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            content: 邮件内容

        Returns:
            Dict: 发送结果
        """
        return self.send_email(to_email, subject, content)

    def test_connection(self) -> Dict[str, Any]:
        """
        测试SMTP连接

        Returns:
            Dict: 测试结果
        """
        smtp = None
        try:
            smtp = self._create_smtp_connection()
            return {
                'success': True,
                'message': 'SMTP连接测试成功',
                'smtp_server': self.smtp_config['smtp_server'],
                'sender_email': self.smtp_config['sender_email']
            }
        except Exception as e:
            logger.error(f"SMTP连接测试失败: {str(e)}")
            return {
                'success': False,
                'message': f'SMTP连接测试失败: {str(e)}'
            }
        finally:
            if smtp:
                try:
                    smtp.quit()
                except Exception:
                    pass


# 创建全局实例，方便其他模块调用
send_email_service = QQEmailService()


if __name__ == "__main__":
    # 测试代码
    service = QQEmailService()

    # 测试连接
    print("测试SMTP连接...")
    test_result = service.test_connection()
    print(f"连接测试结果: {test_result}")

    # 发送测试邮件
    if test_result['success']:
        print("\n发送测试邮件...")
        result = service.send_simple_email(
            to_email="test@example.com",
            subject="测试邮件",
            content="这是一封测试邮件，用于验证邮件服务是否正常工作。"
        )
        print(f"发送结果: {result}")