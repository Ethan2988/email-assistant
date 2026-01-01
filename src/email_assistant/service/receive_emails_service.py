"""
QQ邮件接收服务（重构版）
支持通过IMAP协议接收邮件，获取邮件详细内容

重构说明：
- 使用 email_client.py 的 IMAPClient 进行连接管理
- 保留邮件解析逻辑（业务特有）
- 减少重复代码，提高可维护性
"""

import email
import logging
from email.header import decode_header
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import chardet
from .email_client import IMAPClient


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmailMessage:
    """邮件消息类"""

    def __init__(
        self,
        msg_id: str,
        subject: str,
        from_email: str,
        from_name: str,
        to_email: str,
        date: str,
        body: str,
        body_type: str,
        cc: List[str] = None,
        bcc: List[str] = None,
        attachments: List[Dict[str, Any]] = None,
        raw_email: Any = None
    ):
        self.msg_id = msg_id
        self.subject = subject
        self.from_email = from_email
        self.from_name = from_name
        self.to_email = to_email
        self.date = date
        self.body = body
        self.body_type = body_type  # 'plain' or 'html'
        self.cc = cc or []
        self.bcc = bcc or []
        self.attachments = attachments or []
        self.raw_email = raw_email

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'msg_id': self.msg_id,
            'subject': self.subject,
            'from_email': self.from_email,
            'from_name': self.from_name,
            'to_email': self.to_email,
            'date': self.date,
            'body': self.body,
            'body_type': self.body_type,
            'cc': self.cc,
            'bcc': self.bcc,
            'attachments': self.attachments,
        }

    def __repr__(self):
        return f"EmailMessage(from={self.from_email}, subject={self.subject}, date={self.date})"


class ReceiveEmailsService:
    """
    QQ邮件接收服务（重构版）

    重构说明：
    - 使用 IMAPClient 管理连接，无需手动创建和关闭连接
    - 使用 IMAPClient 的基础操作（搜索、获取、设置标志）
    - 保留邮件解析相关的业务逻辑
    - 简化代码，减少重复

    使用方式：
        # 方式1：直接使用（内部会管理连接）
        service = ReceiveEmailsService()
        result = service.receive_latest_emails(count=10)

        # 方式2：使用上下文管理器（推荐）
        with ReceiveEmailsService() as service:
            result = service.receive_latest_emails(count=10)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化邮件接收服务

        Args:
            config_path: 配置文件路径
        """
        # 使用 IMAPClient 进行连接管理
        self.client = IMAPClient(config_path)
        logger.info("ReceiveEmailsService 初始化完成（使用 IMAPClient）")

    def _decode_header_value(self, header_value: bytes) -> str:
        """
        解码邮件头

        Args:
            header_value: 邮件头字节数据

        Returns:
            str: 解码后的字符串
        """
        if header_value is None:
            return ""

        try:
            decoded_parts = decode_header(header_value)
            result = ""
            for content, encoding in decoded_parts:
                if isinstance(content, bytes):
                    if encoding:
                        result += content.decode(encoding)
                    else:
                        # 如果没有指定编码，尝试检测
                        detected = chardet.detect(content)
                        result += content.decode(detected['encoding'] or 'utf-8', errors='ignore')
                else:
                    result += str(content)
            return result
        except Exception as e:
            logger.warning(f"解码邮件头失败: {str(e)}")
            return str(header_value)

    def _extract_email_address(self, addr_str: str) -> tuple:
        """
        从地址字符串中提取邮箱和名称

        Args:
            addr_str: 地址字符串，格式如 "Name <email@example.com>" 或 "email@example.com"

        Returns:
            tuple: (name, email_address)
        """
        try:
            # 格式可能是: "Name <email@example.com>" 或 "email@example.com"
            if '<' in addr_str and '>' in addr_str:
                name = addr_str[:addr_str.index('<')].strip().strip('"')
                email_addr = addr_str[addr_str.index('<') + 1:addr_str.index('>')].strip()
                return name, email_addr
            else:
                return "", addr_str.strip()
        except Exception:
            return "", addr_str

    def _get_email_body(self, msg: email.message.Message) -> tuple:
        """
        获取邮件正文

        Args:
            msg: email.message.Message 对象

        Returns:
            tuple: (body_content, body_type) - 正文内容和类型
        """
        body = ""
        body_type = "plain"

        try:
            # 优先获取HTML正文
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))

                    # 跳过附件
                    if "attachment" in content_disposition:
                        continue

                    # 优先使用HTML
                    if content_type == "text/html" and not body:
                        try:
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='ignore')
                            body_type = "html"
                        except Exception:
                            pass

                    # 如果没有HTML，使用纯文本
                    elif content_type == "text/plain" and not body:
                        try:
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='ignore')
                            body_type = "plain"
                        except Exception:
                            pass
            else:
                # 非多部分邮件
                try:
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='ignore')
                    content_type = msg.get_content_type()
                    body_type = "html" if "html" in content_type else "plain"
                except Exception:
                    body = str(msg.get_payload())

        except Exception as e:
            logger.error(f"获取邮件正文失败: {str(e)}")

        return body, body_type

    def _extract_attachments(self, msg: email.message.Message) -> List[Dict[str, Any]]:
        """
        提取附件信息

        Args:
            msg: email.message.Message 对象

        Returns:
            List[Dict]: 附件信息列表
        """
        attachments = []

        try:
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header_value(filename)
                        file_size = len(part.get_payload(decode=True) or b'')

                        attachments.append({
                            'filename': filename,
                            'size': file_size,
                            'content_type': part.get_content_type(),
                        })

        except Exception as e:
            logger.warning(f"提取附件信息失败: {str(e)}")

        return attachments

    def _parse_email_message(self, msg: email.message.Message, msg_id: str) -> EmailMessage:
        """
        解析邮件消息为 EmailMessage 对象

        Args:
            msg: email.message.Message 对象
            msg_id: 邮件 ID

        Returns:
            EmailMessage: 解析后的邮件对象
        """
        try:
            # 解析邮件头
            subject = self._decode_header_value(msg.get('Subject', ''))
            from_header = self._decode_header_value(msg.get('From', ''))
            to_header = self._decode_header_value(msg.get('To', ''))
            date_header = msg.get('Date', '')
            cc_header = self._decode_header_value(msg.get('Cc', ''))

            # 提取发件人信息
            from_name, from_email = self._extract_email_address(from_header)

            # 提取收件人信息
            _, to_email = self._extract_email_address(to_header)

            # 解析抄送
            cc_list = []
            if cc_header:
                cc_addrs = cc_header.split(',')
                for addr in cc_addrs:
                    _, cc_email = self._extract_email_address(addr.strip())
                    if cc_email:
                        cc_list.append(cc_email)

            # 格式化日期
            try:
                date_tuple = email.utils.parsedate_tz(date_header)
                if date_tuple:
                    timestamp = email.utils.mktime_tz(date_tuple)
                    date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    date_str = date_header
            except Exception:
                date_str = date_header

            # 获取邮件正文
            body, body_type = self._get_email_body(msg)

            # 提取附件
            attachments = self._extract_attachments(msg)

            return EmailMessage(
                msg_id=msg_id,
                subject=subject,
                from_email=from_email,
                from_name=from_name,
                to_email=to_email,
                date=date_str,
                body=body,
                body_type=body_type,
                cc=cc_list,
                bcc=[],
                attachments=attachments,
                raw_email=msg
            )

        except Exception as e:
            logger.error(f"解析邮件消息失败: {str(e)}")
            raise

    def receive_emails(
        self,
        count: int = 30,
        folder: str = 'INBOX',
        mark_as_read: bool = False,
        filter_unseen: bool = False
    ) -> Dict[str, Any]:
        """
        接收邮件（重构版 - 使用 IMAPClient）

        Args:
            count: 接收邮件数量，默认30封
            folder: 邮箱文件夹，默认'INBOX'
            mark_as_read: 是否标记为已读
            filter_unseen: 是否只获取未读邮件

        Returns:
            Dict: 接收结果，包含success、emails、total、count等信息

        示例：
            # 接收最新10封邮件
            result = service.receive_emails(count=10)

            # 只接收未读邮件
            result = service.receive_emails(filter_unseen=True)

            # 接收并标记为已读
            result = service.receive_emails(mark_as_read=True)
        """
        try:
            # 构建搜索条件
            criteria = 'UNSEEN' if filter_unseen else 'ALL'

            # 使用 IMAPClient 搜索邮件
            logger.info(f"正在搜索邮件，条件: {criteria}, 文件夹: {folder}")
            email_ids = self.client.search_emails(criteria=criteria, folder=folder)
            total_count = len(email_ids)

            # 限制数量
            if count > 0:
                email_ids = email_ids[-count:]  # 获取最新的count封邮件

            logger.info(f"找到 {total_count} 封邮件，将获取最新的 {len(email_ids)} 封")

            # 解析邮件
            emails = []
            msg_ids_to_mark = []  # 需要标记为已读的邮件ID

            for msg_id in reversed(email_ids):  # 最新的邮件在前
                try:
                    # 使用 IMAPClient 获取邮件
                    raw_email = self.client.fetch_email(msg_id, folder=folder)

                    if raw_email:
                        # 解析邮件
                        msg = email.message_from_bytes(raw_email)
                        msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id

                        # 解析邮件内容
                        email_msg = self._parse_email_message(msg, msg_id_str)
                        emails.append(email_msg)

                        # 记录需要标记为已读的邮件
                        if mark_as_read:
                            msg_ids_to_mark.append(msg_id_str)

                except Exception as e:
                    logger.error(f"解析邮件 {msg_id} 失败: {str(e)}")
                    continue

            # 批量标记为已读
            if mark_as_read and msg_ids_to_mark:
                logger.info(f"正在标记 {len(msg_ids_to_mark)} 封邮件为已读")
                mark_result = self.client.store_flags(
                    msg_ids=msg_ids_to_mark,
                    flag_command='+FLAGS',
                    flags='\\Seen',
                    folder=folder
                )
                if mark_result['success']:
                    logger.info(f"成功标记 {mark_result['count']} 封邮件为已读")

            logger.info(f"成功接收 {len(emails)} 封邮件")

            return {
                'success': True,
                'emails': emails,
                'count': len(emails),
                'total': total_count,
                'folder': folder,
                'message': f'成功接收 {len(emails)} 封邮件'
            }

        except Exception as e:
            logger.error(f"接收邮件失败: {str(e)}")
            return {
                'success': False,
                'emails': [],
                'count': 0,
                'total': 0,
                'folder': folder,
                'message': f'接收邮件失败: {str(e)}',
                'error_type': type(e).__name__
            }

    def receive_latest_emails(self, count: int = 30) -> Dict[str, Any]:
        """
        接收最新的邮件（便捷方法）

        Args:
            count: 接收邮件数量，默认30封

        Returns:
            Dict: 接收结果

        示例：
            result = service.receive_latest_emails(count=10)
        """
        return self.receive_emails(count=count, filter_unseen=False)

    def receive_unread_emails(self, count: int = 30) -> Dict[str, Any]:
        """
        接收未读邮件（便捷方法）

        Args:
            count: 接收邮件数量，默认30封

        Returns:
            Dict: 接收结果

        示例：
            result = service.receive_unread_emails(count=10)
        """
        return self.receive_emails(count=count, filter_unseen=True)

    def get_mailbox_status(self, folder: str = 'INBOX') -> Dict[str, Any]:
        """
        获取邮箱状态（重构版 - 使用 IMAPClient）

        Args:
            folder: 文件夹名称

        Returns:
            Dict: 邮箱状态信息

        示例：
            status = service.get_mailbox_status('INBOX')
            print(f"总邮件: {status['total_messages']}")
            print(f"未读: {status['unread_messages']}")
        """
        try:
            return self.client.get_mailbox_status(folder)
        except Exception as e:
            logger.error(f"获取邮箱状态失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取邮箱状态失败: {str(e)}'
            }

    def list_folders(self) -> Dict[str, Any]:
        """
        列出所有邮箱文件夹（重构版 - 使用 IMAPClient）

        Returns:
            Dict: 文件夹列表

        示例：
            folders = service.list_folders()
            print(f"可用文件夹: {folders['folders']}")
        """
        try:
            return self.client.list_folders()
        except Exception as e:
            logger.error(f"列出文件夹失败: {str(e)}")
            return {
                'success': False,
                'folders': [],
                'message': f'列出文件夹失败: {str(e)}'
            }

    def close(self):
        """关闭服务连接"""
        self.client.close()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()


# 创建全局实例
receive_emails_service = ReceiveEmailsService()


if __name__ == "__main__":
    """测试代码"""
    import json

    print("=== 测试邮件接收服务（重构版）===\n")

    # 测试：使用上下文管理器
    with ReceiveEmailsService() as service:
        # 1. 获取邮箱状态
        print("1. 获取邮箱状态...")
        status = service.get_mailbox_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))

        # 2. 列出文件夹
        print("\n2. 列出邮箱文件夹...")
        folders = service.list_folders()
        print(json.dumps(folders, indent=2, ensure_ascii=False))

        # 3. 接收最新5封邮件
        print("\n3. 接收最新5封邮件...")
        result = service.receive_latest_emails(count=5)
        print(f"接收结果: {result['message']}")
        print(f"共 {result['count']} 封邮件，总计 {result['total']} 封")

        # 打印邮件详情
        for i, email_msg in enumerate(result['emails'], 1):
            print(f"\n邮件 {i}:")
            print(f"  主题: {email_msg.subject}")
            print(f"  发件人: {email_msg.from_name} <{email_msg.from_email}>")
            print(f"  日期: {email_msg.date}")
            print(f"  正文长度: {len(email_msg.body)} 字符")
            print(f"  附件数: {len(email_msg.attachments)}")
            if email_msg.attachments:
                for att in email_msg.attachments:
                    print(f"    - {att['filename']} ({att['size']} bytes)")

        # 4. 测试接收并标记为已读
        print("\n4. 测试接收并标记为已读...")
        if result['count'] > 0:
            test_result = service.receive_emails(count=1, mark_as_read=True)
            print(f"测试结果: {test_result['message']}")
