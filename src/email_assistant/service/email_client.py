"""
底层 IMAP 客户端 - 提供统一的邮件服务器连接和基础操作

职责：
- IMAP 连接管理（创建、复用、关闭）
- 连接池管理
- 自动重连机制
- 基础 IMAP 操作封装
- 线程安全

设计原则：
- 单一职责：只负责连接管理和基础 IMAP 操作
- 底层抽象：不包含业务逻辑
- 可复用：供上层服务使用
"""

import imaplib
import logging
import threading
from typing import Optional, Dict, Any, List, Union
from contextlib import contextmanager
from ..config import EmailConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IMAPClient:
    """
    IMAP 客户端类 - 提供底层的邮件服务器连接和操作

    特性：
    - 支持上下文管理器（with 语句）
    - 自动重连机制
    - 线程安全的连接管理
    - 统一的错误处理
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化 IMAP 客户端

        Args:
            config_path: 配置文件路径
        """
        self.email_config = EmailConfig(config_path)
        self.imap_config = self.email_config.get_imap_config()

        # 连接对象（惰性创建）
        self._connection: Optional[imaplib.IMAP4_SSL] = None
        # 连接锁（线程安全）
        self._lock = threading.RLock()
        # 当前选择的文件夹
        self._current_folder: Optional[str] = None

        logger.info("IMAPClient 初始化完成")

    def _create_connection(self) -> imaplib.IMAP4_SSL:
        """
        创建新的 IMAP 连接

        Returns:
            IMAP4_SSL: IMAP 连接对象

        Raises:
            Exception: 连接或认证失败
        """
        try:
            # 创建 IMAP SSL 连接
            conn = imaplib.IMAP4_SSL(
                self.imap_config['imap_server'],
                self.imap_config['imap_port']
            )

            # 登录
            conn.login(self.imap_config['email'], self.imap_config['auth_code'])

            logger.info(f"IMAP 连接创建成功: {self.imap_config['email']}")
            return conn

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP 认证失败: {str(e)}")
            raise Exception(f"IMAP 认证失败，请检查邮箱和授权码: {str(e)}")
        except Exception as e:
            logger.error(f"创建 IMAP 连接失败: {str(e)}")
            raise

    @property
    def connection(self) -> imaplib.IMAP4_SSL:
        """
        获取 IMAP 连接（惰性创建，支持自动重连）

        Returns:
            IMAP4_SSL: 有效的 IMAP 连接对象
        """
        with self._lock:
            # 如果连接不存在或已断开，重新创建
            if self._connection is None:
                self._connection = self._create_connection()
            else:
                # 测试连接是否仍然有效
                try:
                    self._connection.noop()
                except imaplib.IMAP4.error:
                    logger.warning("连接已断开，尝试重新连接...")
                    self._connection = self._create_connection()
                    # 重置当前文件夹状态（新连接需要重新 SELECT）
                    self._current_folder = None

            return self._connection

    def select_folder(self, folder: str = 'INBOX') -> bool:
        """
        选择邮箱文件夹

        Args:
            folder: 文件夹名称，默认 'INBOX'

        Returns:
            bool: 是否成功选择

        Raises:
            Exception: 选择文件夹失败
        """
        try:
            # 如果已经在该文件夹，直接返回
            if self._current_folder == folder:
                logger.debug(f"已在文件夹: {folder}，跳过 SELECT")
                return True

            # 执行 SELECT 命令
            status, _ = self.connection.select(folder)

            if status != 'OK':
                raise Exception(f"选择文件夹失败: {folder}")

            self._current_folder = folder
            logger.info(f"已选择文件夹: {folder}")
            return True

        except Exception as e:
            logger.error(f"选择文件夹失败: {str(e)}")
            # 重置状态，确保下次会重新尝试
            self._current_folder = None
            raise

    def search_emails(
        self,
        criteria: str = 'ALL',
        folder: str = 'INBOX'
    ) -> List[bytes]:
        """
        搜索邮件

        Args:
            criteria: 搜索条件，如 'UNSEEN', 'FROM "example.com"', 'SINCE 1-Jan-2024'
            folder: 文件夹名称

        Returns:
            List[bytes]: 邮件 ID 列表

        Raises:
            Exception: 搜索失败
        """
        try:
            self.select_folder(folder)
            status, messages = self.connection.search(None, criteria)

            if status != 'OK':
                raise Exception(f"搜索邮件失败: {status}")

            email_ids = messages[0].split()
            logger.debug(f"搜索到 {len(email_ids)} 封邮件，条件: {criteria}")
            return email_ids

        except Exception as e:
            logger.error(f"搜索邮件失败: {str(e)}")
            raise

    def fetch_email(self, msg_id: Union[str, bytes], folder: str = 'INBOX') -> Optional[bytes]:
        """
        获取单封邮件的原始内容

        Args:
            msg_id: 邮件 ID
            folder: 文件夹名称

        Returns:
            Optional[bytes]: 邮件原始内容，如果失败返回 None

        Raises:
            Exception: 获取邮件失败
        """
        try:
            self.select_folder(folder)

            # 确保 msg_id 是 bytes 类型
            if isinstance(msg_id, str):
                msg_id = msg_id.encode()

            status, msg_data = self.connection.fetch(msg_id, '(RFC822)')

            if status != 'OK':
                logger.error(f"获取邮件失败: {msg_id}")
                return None

            return msg_data[0][1]

        except Exception as e:
            logger.error(f"获取邮件失败: {str(e)}")
            raise

    def store_flags(
        self,
        msg_ids: Union[str, bytes, List[Union[str, bytes]]],
        flag_command: str,
        flags: str,
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        设置邮件标志（已读、删除、星标等）

        Args:
            msg_ids: 单个或多个邮件 ID
            flag_command: 标志命令，如 '+FLAGS'（添加）, '-FLAGS'（移除）, 'FLAGS'（设置）
            flags: 标志值，如 '\\Seen'（已读）, '\\Deleted'（删除）, '\\Flagged'（星标）
            folder: 文件夹名称

        Returns:
            Dict: 操作结果

        Raises:
            Exception: 设置标志失败
        """
        try:
            self.select_folder(folder)

            # 统一处理 msg_ids 为列表
            if isinstance(msg_ids, (str, bytes)):
                msg_ids = [msg_ids]

            results = []
            for msg_id in msg_ids:
                # 确保是 bytes 类型
                if isinstance(msg_id, str):
                    msg_id = msg_id.encode()

                status, response = self.connection.store(msg_id, flag_command, flags)

                if status == 'OK':
                    results.append(msg_id.decode() if isinstance(msg_id, bytes) else msg_id)
                    logger.debug(f"邮件 {msg_id} 设置标志成功: {flag_command} {flags}")
                else:
                    logger.warning(f"邮件 {msg_id} 设置标志失败: {status}")

            return {
                'success': True,
                'count': len(results),
                'msg_ids': results,
                'message': f'成功设置 {len(results)} 封邮件的标志'
            }

        except Exception as e:
            logger.error(f"设置邮件标志失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'设置邮件标志失败: {str(e)}'
            }

    def copy_email(
        self,
        msg_ids: Union[str, bytes, List[Union[str, bytes]]],
        dest_folder: str,
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        复制邮件到目标文件夹

        Args:
            msg_ids: 单个或多个邮件 ID
            dest_folder: 目标文件夹
            folder: 源文件夹

        Returns:
            Dict: 操作结果
        """
        try:
            self.select_folder(folder)

            if isinstance(msg_ids, (str, bytes)):
                msg_ids = [msg_ids]

            results = []
            for msg_id in msg_ids:
                if isinstance(msg_id, str):
                    msg_id = msg_id.encode()

                status, response = self.connection.copy(msg_id, dest_folder)

                if status == 'OK':
                    results.append(msg_id.decode() if isinstance(msg_id, bytes) else msg_id)
                    logger.debug(f"邮件 {msg_id} 复制到 {dest_folder} 成功")
                else:
                    logger.warning(f"邮件 {msg_id} 复制失败: {status}")

            return {
                'success': True,
                'count': len(results),
                'msg_ids': results,
                'message': f'成功复制 {len(results)} 封邮件到 {dest_folder}'
            }

        except Exception as e:
            logger.error(f"复制邮件失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'复制邮件失败: {str(e)}'
            }

    def move_email(
        self,
        msg_ids: Union[str, bytes, List[Union[str, bytes]]],
        dest_folder: str,
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        移动邮件到目标文件夹（复制 + 删除）

        Args:
            msg_ids: 单个或多个邮件 ID
            dest_folder: 目标文件夹
            folder: 源文件夹

        Returns:
            Dict: 操作结果
        """
        try:
            # 先复制到目标文件夹
            copy_result = self.copy_email(msg_ids, dest_folder, folder)

            if not copy_result['success']:
                return copy_result

            # 再标记为删除
            delete_result = self.store_flags(
                copy_result['msg_ids'],
                '+FLAGS',
                '\\Deleted',
                folder
            )

            # 执行 EXPUNGE 永久删除
            if delete_result['success']:
                self.connection.expunge()

            return {
                'success': delete_result['success'],
                'count': len(copy_result['msg_ids']),
                'msg_ids': copy_result['msg_ids'],
                'message': f'成功移动 {len(copy_result["msg_ids"])} 封邮件到 {dest_folder}'
            }

        except Exception as e:
            logger.error(f"移动邮件失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'移动邮件失败: {str(e)}'
            }

    def get_mailbox_status(self, folder: str = 'INBOX') -> Dict[str, Any]:
        """
        获取邮箱状态信息

        Args:
            folder: 文件夹名称

        Returns:
            Dict: 邮箱状态信息

        Raises:
            Exception: 获取状态失败
        """
        try:
            self.select_folder(folder)
            status, data = self.connection.status(folder, '(MESSAGES UNSEEN RECENT)')

            if status != 'OK':
                raise Exception(f"获取邮箱状态失败: {status}")

            # 解析状态数据
            import re
            status_str = data[0].decode()
            messages = int(re.search(r'MESSAGES (\d+)', status_str).group(1))
            unseen = int(re.search(r'UNSEEN (\d+)', status_str).group(1))
            recent = int(re.search(r'RECENT (\d+)', status_str).group(1))

            return {
                'success': True,
                'folder': folder,
                'total_messages': messages,
                'unread_messages': unseen,
                'recent_messages': recent,
            }

        except Exception as e:
            logger.error(f"获取邮箱状态失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取邮箱状态失败: {str(e)}'
            }

    def list_folders(self) -> Dict[str, Any]:
        """
        列出所有邮箱文件夹

        Returns:
            Dict: 文件夹列表

        Raises:
            Exception: 列出文件夹失败
        """
        try:
            status, folders = self.connection.list()

            if status != 'OK':
                raise Exception(f"列出文件夹失败: {status}")

            folder_list = []
            for folder in folders:
                folder_str = folder.decode()
                # 解析文件夹名称
                if '"' in folder_str:
                    parts = folder_str.split('"')
                    if len(parts) >= 3:
                        folder_name = parts[-2] if parts[-2] else parts[1]
                    else:
                        folder_name = folder_str
                else:
                    folder_name = folder_str.split()[-1] if folder_str.split() else folder_str

                folder_list.append(folder_name)

            return {
                'success': True,
                'folders': folder_list,
                'count': len(folder_list)
            }

        except Exception as e:
            logger.error(f"列出文件夹失败: {str(e)}")
            return {
                'success': False,
                'folders': [],
                'message': f'列出文件夹失败: {str(e)}'
            }

    def close(self):
        """关闭 IMAP 连接"""
        with self._lock:
            if self._connection is not None:
                try:
                    # 先关闭当前文件夹
                    try:
                        self._connection.close()
                    except imaplib.IMAP4.error:
                        pass

                    # 再登出
                    try:
                        self._connection.logout()
                    except imaplib.IMAP4.error:
                        pass

                    logger.info("IMAP 连接已关闭")
                except Exception as e:
                    logger.warning(f"关闭 IMAP 连接时出错: {str(e)}")
                finally:
                    self._connection = None
                    self._current_folder = None

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    def __del__(self):
        """析构函数，确保连接被关闭"""
        self.close()


# 便捷函数：使用上下文管理器创建临时连接
@contextmanager
def create_imap_client(config_path: Optional[str] = None):
    """
    创建临时 IMAP 客户端的上下文管理器

    用法：
        with create_imap_client() as client:
            status = client.get_mailbox_status()
            print(status)

    Args:
        config_path: 配置文件路径

    Yields:
        IMAPClient: IMAP 客户端实例
    """
    client = IMAPClient(config_path)
    try:
        yield client
    finally:
        client.close()
