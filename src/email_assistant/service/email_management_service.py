"""
邮件管理服务 - 负责邮件状态管理和组织

职责：
- 邮件状态管理：标记已读/未读、标记星标/重要
- 邮件组织：移动到文件夹、删除、归档
- 批量操作：批量标记、批量移动

架构：
- 依赖 email_client.py 提供的底层 IMAP 操作
- 不包含邮件接收功能（由 receive_emails_service.py 负责）
- 不包含邮件监听功能（由 email_listener.py 负责）

设计原则：
- 单一职责：只负责邮件的管理操作
- 高层抽象：提供业务友好的接口
- 可复用：任何地方都可以调用
"""

import logging
from typing import Union, List, Dict, Any, Optional
from .email_client import IMAPClient, create_imap_client

logger = logging.getLogger(__name__)


class EmailManagementService:
    """
    邮件管理服务类

    提供邮件状态管理和组织功能，包括：
    - 标记已读/未读
    - 标记星标
    - 移动到文件夹
    - 删除邮件
    - 邮箱状态查询

    使用方式：
        # 方式1：手动管理连接
        service = EmailManagementService()
        result = service.mark_as_read(msg_id)
        service.close()

        # 方式2：使用上下文管理器（推荐）
        with EmailManagementService() as service:
            result = service.mark_as_read(msg_id)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化邮件管理服务

        Args:
            config_path: 配置文件路径
        """
        self.client = IMAPClient(config_path)
        logger.info("EmailManagementService 初始化完成")

    def mark_as_read(
        self,
        msg_ids: Union[str, List[str]],
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        标记邮件为已读

        Args:
            msg_ids: 单个邮件 ID 或邮件 ID 列表
            folder: 文件夹名称，默认 'INBOX'

        Returns:
            Dict: 操作结果
                {
                    'success': True,
                    'count': 2,
                    'msg_ids': ['123', '124'],
                    'message': '成功标记 2 封邮件为已读'
                }

        示例：
            # 标记单封邮件
            result = service.mark_as_read('12345')

            # 批量标记
            result = service.mark_as_read(['12345', '12346', '12347'])
        """
        try:
            logger.info(f"正在标记 {len(msg_ids) if isinstance(msg_ids, list) else 1} 封邮件为已读")

            result = self.client.store_flags(
                msg_ids=msg_ids,
                flag_command='+FLAGS',
                flags='\\Seen',
                folder=folder
            )

            if result['success']:
                result['message'] = f"成功标记 {result['count']} 封邮件为已读"
                logger.info(result['message'])

            return result

        except Exception as e:
            logger.error(f"标记已读失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'标记已读失败: {str(e)}'
            }

    def mark_as_unread(
        self,
        msg_ids: Union[str, List[str]],
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        标记邮件为未读

        Args:
            msg_ids: 单个邮件 ID 或邮件 ID 列表
            folder: 文件夹名称，默认 'INBOX'

        Returns:
            Dict: 操作结果

        示例：
            result = service.mark_as_unread(['12345', '12346'])
        """
        try:
            logger.info(f"正在标记 {len(msg_ids) if isinstance(msg_ids, list) else 1} 封邮件为未读")

            result = self.client.store_flags(
                msg_ids=msg_ids,
                flag_command='-FLAGS',
                flags='\\Seen',
                folder=folder
            )

            if result['success']:
                result['message'] = f"成功标记 {result['count']} 封邮件为未读"
                logger.info(result['message'])

            return result

        except Exception as e:
            logger.error(f"标记未读失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'标记未读失败: {str(e)}'
            }

    def mark_as_starred(
        self,
        msg_ids: Union[str, List[str]],
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        标记邮件为星标（重要）

        Args:
            msg_ids: 单个邮件 ID 或邮件 ID 列表
            folder: 文件夹名称，默认 'INBOX'

        Returns:
            Dict: 操作结果

        示例：
            result = service.mark_as_starred('12345')
        """
        try:
            logger.info(f"正在标记 {len(msg_ids) if isinstance(msg_ids, list) else 1} 封邮件为星标")

            result = self.client.store_flags(
                msg_ids=msg_ids,
                flag_command='+FLAGS',
                flags='\\Flagged',
                folder=folder
            )

            if result['success']:
                result['message'] = f"成功标记 {result['count']} 封邮件为星标"
                logger.info(result['message'])

            return result

        except Exception as e:
            logger.error(f"标记星标失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'标记星标失败: {str(e)}'
            }

    def remove_starred(
        self,
        msg_ids: Union[str, List[str]],
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        移除邮件的星标标记

        Args:
            msg_ids: 单个邮件 ID 或邮件 ID 列表
            folder: 文件夹名称，默认 'INBOX'

        Returns:
            Dict: 操作结果
        """
        try:
            logger.info(f"正在移除 {len(msg_ids) if isinstance(msg_ids, list) else 1} 封邮件的星标")

            result = self.client.store_flags(
                msg_ids=msg_ids,
                flag_command='-FLAGS',
                flags='\\Flagged',
                folder=folder
            )

            if result['success']:
                result['message'] = f"成功移除 {result['count']} 封邮件的星标"
                logger.info(result['message'])

            return result

        except Exception as e:
            logger.error(f"移除星标失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'移除星标失败: {str(e)}'
            }

    def delete_emails(
        self,
        msg_ids: Union[str, List[str]],
        folder: str = 'INBOX',
        permanent: bool = False
    ) -> Dict[str, Any]:
        """
        删除邮件

        Args:
            msg_ids: 单个邮件 ID 或邮件 ID 列表
            folder: 文件夹名称，默认 'INBOX'
            permanent: 是否永久删除（True）或移到回收站（False）

        Returns:
            Dict: 操作结果

        注意：
            - permanent=False: 标记为删除（移到回收站）
            - permanent=True: 永久删除（不可恢复）

        示例：
            # 移到回收站
            result = service.delete_emails('12345', permanent=False)

            # 永久删除
            result = service.delete_emails('12345', permanent=True)
        """
        try:
            logger.info(f"正在删除 {len(msg_ids) if isinstance(msg_ids, list) else 1} 封邮件（永久={permanent}）")

            if permanent:
                # 永久删除：先标记删除，再执行 expunge
                result = self.client.store_flags(
                    msg_ids=msg_ids,
                    flag_command='+FLAGS',
                    flags='\\Deleted',
                    folder=folder
                )

                if result['success']:
                    # 执行永久删除
                    self.client.connection.expunge()
                    result['message'] = f"成功永久删除 {result['count']} 封邮件"
                    logger.info(result['message'])
            else:
                # 移到回收站：先标记删除
                result = self.client.store_flags(
                    msg_ids=msg_ids,
                    flag_command='+FLAGS',
                    flags='\\Deleted',
                    folder=folder
                )

                if result['success']:
                    result['message'] = f"成功将 {result['count']} 封邮件移到回收站"
                    logger.info(result['message'])

            return result

        except Exception as e:
            logger.error(f"删除邮件失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'删除邮件失败: {str(e)}'
            }

    def move_to_folder(
        self,
        msg_ids: Union[str, List[str]],
        dest_folder: str,
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        移动邮件到指定文件夹

        Args:
            msg_ids: 单个邮件 ID 或邮件 ID 列表
            dest_folder: 目标文件夹名称
            folder: 源文件夹名称，默认 'INBOX'

        Returns:
            Dict: 操作结果

        示例：
            # 移动到归档文件夹
            result = service.move_to_folder('12345', 'Archive')

            # 批量移动到工作文件夹
            result = service.move_to_folder(['12345', '12346'], 'Work')
        """
        try:
            logger.info(f"正在移动 {len(msg_ids) if isinstance(msg_ids, list) else 1} 封邮件到 {dest_folder}")

            result = self.client.move_email(
                msg_ids=msg_ids,
                dest_folder=dest_folder,
                folder=folder
            )

            if result['success']:
                logger.info(result['message'])

            return result

        except Exception as e:
            logger.error(f"移动邮件失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'移动邮件失败: {str(e)}'
            }

    def copy_to_folder(
        self,
        msg_ids: Union[str, List[str]],
        dest_folder: str,
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        复制邮件到指定文件夹（不删除原邮件）

        Args:
            msg_ids: 单个邮件 ID 或邮件 ID 列表
            dest_folder: 目标文件夹名称
            folder: 源文件夹名称，默认 'INBOX'

        Returns:
            Dict: 操作结果

        示例：
            # 复制到备份文件夹
            result = service.copy_to_folder('12345', 'Backup')
        """
        try:
            logger.info(f"正在复制 {len(msg_ids) if isinstance(msg_ids, list) else 1} 封邮件到 {dest_folder}")

            result = self.client.copy_email(
                msg_ids=msg_ids,
                dest_folder=dest_folder,
                folder=folder
            )

            if result['success']:
                result['message'] = f"成功复制 {result['count']} 封邮件到 {dest_folder}"
                logger.info(result['message'])

            return result

        except Exception as e:
            logger.error(f"复制邮件失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'复制邮件失败: {str(e)}'
            }

    def get_mailbox_status(self, folder: str = 'INBOX') -> Dict[str, Any]:
        """
        获取邮箱状态信息

        Args:
            folder: 文件夹名称，默认 'INBOX'

        Returns:
            Dict: 邮箱状态
                {
                    'success': True,
                    'folder': 'INBOX',
                    'total_messages': 100,
                    'unread_messages': 5,
                    'recent_messages': 2
                }

        示例：
            status = service.get_mailbox_status('INBOX')
            print(f"未读邮件: {status['unread_messages']}")
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
        列出所有邮箱文件夹

        Returns:
            Dict: 文件夹列表
                {
                    'success': True,
                    'folders': ['INBOX', 'Sent', 'Drafts', 'Trash'],
                    'count': 4
                }

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

    def search_emails(
        self,
        criteria: str = 'UNSEEN',
        folder: str = 'INBOX'
    ) -> Dict[str, Any]:
        """
        搜索邮件（返回邮件 ID 列表）

        Args:
            criteria: IMAP 搜索条件
                     常用条件：
                     - 'ALL': 所有邮件
                     - 'UNSEEN': 未读邮件
                     - 'SEEN': 已读邮件
                     - 'FLAGGED': 星标邮件
                     - 'FROM "example.com"': 来自特定发件人
                     - 'SUBJECT "test"': 主题包含关键词
                     - 'SINCE 1-Jan-2024': 某日期之后的邮件
            folder: 文件夹名称，默认 'INBOX'

        Returns:
            Dict: 搜索结果
                {
                    'success': True,
                    'count': 5,
                    'msg_ids': ['123', '124', '125', '126', '127']
                }

        示例：
            # 查找所有未读邮件
            result = service.search_emails('UNSEEN')

            # 查找特定发件人的邮件
            result = service.search_emails('FROM "example.com"')

            # 查找星标邮件
            result = service.search_emails('FLAGGED')
        """
        try:
            email_ids = self.client.search_emails(criteria=criteria, folder=folder)

            return {
                'success': True,
                'count': len(email_ids),
                'msg_ids': [msg_id.decode() if isinstance(msg_id, bytes) else msg_id for msg_id in email_ids],
                'folder': folder,
                'criteria': criteria
            }

        except Exception as e:
            logger.error(f"搜索邮件失败: {str(e)}")
            return {
                'success': False,
                'count': 0,
                'msg_ids': [],
                'error': str(e)
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


# 创建全局实例（可选，但不推荐使用全局实例）
# email_management_service = EmailManagementService()


if __name__ == "__main__":
    """测试代码"""
    import json

    print("=== 测试邮件管理服务 ===\n")

    # 测试：使用上下文管理器
    with EmailManagementService() as service:
        # 1. 获取邮箱状态
        print("1. 获取邮箱状态...")
        status = service.get_mailbox_status('INBOX')
        print(json.dumps(status, indent=2, ensure_ascii=False))

        # 2. 列出文件夹
        print("\n2. 列出文件夹...")
        folders = service.list_folders()
        print(json.dumps(folders, indent=2, ensure_ascii=False))

        # 3. 搜索未读邮件
        print("\n3. 搜索未读邮件...")
        unread = service.search_emails('UNSEEN')
        print(f"找到 {unread['count']} 封未读邮件")

        if unread['count'] > 0:
            # 4. 标记第一封未读邮件为已读
            first_unread_id = unread['msg_ids'][0]
            print(f"\n4. 标记邮件 {first_unread_id} 为已读...")
            mark_result = service.mark_as_read(first_unread_id)
            print(json.dumps(mark_result, indent=2, ensure_ascii=False))

            # 5. 标记为星标
            print(f"\n5. 标记邮件 {first_unread_id} 为星标...")
            star_result = service.mark_as_starred(first_unread_id)
            print(json.dumps(star_result, indent=2, ensure_ascii=False))
        else:
            print("\n4-5. 没有未读邮件可供测试标记功能")
