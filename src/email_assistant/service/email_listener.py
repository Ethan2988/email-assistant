"""
邮件监听服务
支持 IMAP IDLE 实时推送 + 定时轮询备用方案
在独立线程中运行，不阻塞主线程
"""

import threading
import time
import logging
import socket
import imaplib
from typing import Callable, Dict, Any, List, Optional
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future
from .receive_emails_service import EmailMessage, ReceiveEmailsService
from .email_client import IMAPClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ListenerMode(Enum):
    """监听模式"""
    IDLE = "idle"           # IMAP IDLE 实时推送
    POLLING = "polling"     # 定时轮询
    STOPPED = "stopped"     # 已停止


class EmailListener:
    """
    邮件监听服务

    功能：
    1. 优先使用 IMAP IDLE 实时监听新邮件
    2. IDLE 失败自动切换到定时轮询
    3. 自动重连和模式切换
    4. 在独立线程中运行
    """

    def __init__(
        self,
        new_email_callback: Callable[[List[EmailMessage]], None],
        imap_client: Optional[IMAPClient] = None,
        polling_interval: int = 60,
        idle_timeout: int = 290,
        max_retries: int = 3,
        folder: str = 'INBOX',
        max_workers: int = 3
    ):
        """
        初始化邮件监听服务

        Args:
            new_email_callback: 新邮件回调函数，接收邮件列表
            imap_client: IMAPClient实例，如果不提供则创建新实例
            polling_interval: 轮询间隔（秒），默认60秒
            idle_timeout: IDLE超时时间（秒），默认290秒（QQ邮箱约5分钟超时）
            max_retries: 最大重试次数，默认3次
            folder: 监听的邮箱文件夹，默认INBOX
            max_workers: 线程池最大工作线程数，默认3个
        """
        self.new_email_callback = new_email_callback
        self.polling_interval = polling_interval
        self.idle_timeout = idle_timeout
        self.max_retries = max_retries
        self.folder = folder
        self.max_workers = max_workers

        # 使用 IMAPClient 管理连接
        self._imap_client = imap_client if imap_client else IMAPClient()

        # 持久化连接的邮件服务（连接复用）
        self._receive_service: Optional[ReceiveEmailsService] = None

        # 状态
        self.mode = ListenerMode.STOPPED
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_uid: Optional[str] = None

        # 线程池（用于异步处理邮件）
        self._executor: Optional[ThreadPoolExecutor] = None
        self._pending_futures: List[Future] = []

        # 统计
        self._stats = {
            'total_received': 0,
            'idle_failures': 0,
            'polling_count': 0,
            'mode_switches': 0,
            'processing_tasks': 0,  # 当前正在处理的任务数
            'completed_tasks': 0,    # 已完成的任务数
            'connection_reuses': 0,  # 连接复用次数（新增）
            'connection_restarts': 0 # 连接重建次数（新增）
        }

    def start(self, initial_sync_count: int = 30) -> bool:
        """
        启动邮件监听服务（连接复用优化版）
        """
        if self._running:
            logger.warning("邮件监听服务已在运行")
            return False

        logger.info("正在启动邮件监听服务...")

        # 初始化线程池
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="EmailProcessor"
        )
        logger.info(f"线程池已初始化，最大工作线程: {self.max_workers}")

        # ✅ 优化：立即初始化持久化连接（连接复用）
        if self._receive_service is None:
            self._receive_service = ReceiveEmailsService()
            self._stats['connection_restarts'] += 1
            logger.info("✓ IMAP 长连接已建立（启动时初始化）")

        # 使用持久化连接同步最近的邮件
        try:
            result = self._receive_service.receive_latest_emails(count=initial_sync_count)

            if result['success'] and result['emails']:
                logger.info(f"已同步 {len(result['emails'])} 封最近邮件")

                if result['emails']:
                    self._last_uid = result['emails'][0].msg_id
                    logger.info(f"最新邮件 UID: {self._last_uid}")
        except Exception as e:
            logger.error(f"初始同步失败: {str(e)}")
            # 如果初始同步失败，关闭连接，下次轮询时会重新建立
            if self._receive_service:
                try:
                    self._receive_service.client.close()
                except:
                    pass
                self._receive_service = None
            # 初始失败不影响后续监听

        # 启动监听线程
        self._running = True
        #self.mode = ListenerMode.IDLE
        self.mode = ListenerMode.POLLING
        self._thread = threading.Thread(
            target=self._run_listener,
            name="EmailListenerThread",
            daemon=True
        )
        self._thread.start()

        # 等待线程启动
        import time
        time.sleep(0.5)  # 短暂等待线程启动

        logger.info(f"邮件监听服务已启动，模式: {self.mode.value}")
    



    def stop(self) -> None:
        """停止邮件监听服务"""
        if not self._running:
            return

        logger.info("正在停止邮件监听服务...")
        self._running = False

        # 关闭线程池（等待现有任务完成）
        if self._executor:
            logger.info("正在等待邮件处理任务完成...")
            pending_count = len(self._pending_futures)
            if pending_count > 0:
                logger.info(f"当前有 {pending_count} 个任务在处理中...")

            # 关闭线程池，不再接受新任务
            self._executor.shutdown(wait=True, timeout=30)
            logger.info("线程池已关闭")

        # 关闭持久化的 IMAP 连接（连接复用版本）
        if self._receive_service:
            try:
                logger.info("正在关闭持久化 IMAP 连接...")
                self._receive_service.client.close()
                logger.info("✓ 持久化 IMAP 连接已关闭")
            except Exception as e:
                logger.warning(f"关闭持久化连接时出错: {str(e)}")
            finally:
                self._receive_service = None

        # 使用 IMAPClient 关闭连接（作为备份）
        self._imap_client.close()

        # 等待线程结束
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        self.mode = ListenerMode.STOPPED
        logger.info("邮件监听服务已停止")

    def _run_listener(self) -> None:
        """监听线程主循环"""
        logger.info("监听线程已启动")

        retry_count = 0
        last_exception = None

        while self._running:
            try:
                logger.info(f"监听循环开始，当前模式: {self.mode}, 重试计数: {retry_count}")
                
                # 优先尝试 IDLE 模式
                # if self.mode != ListenerMode.IDLE and retry_count < self.max_retries:
                #     logger.info("尝试启动 IDLE 模式...")
                #     if self._try_idle_mode():
                #         logger.info("IDLE 模式启动成功")
                #         retry_count = 0  # 成功则重置重试计数
                #         self.mode = ListenerMode.IDLE
                #     else:
                #         retry_count += 1
                #         logger.warning(f"IDLE 模式失败，尝试轮询模式 ({retry_count}/{self.max_retries})")
                #         self.mode = ListenerMode.POLLING
                #         self._stats['mode_switches'] += 1

                # # IDLE 失败或已达最大重试次数，使用轮询模式
                # if self.mode == ListenerMode.POLLING or retry_count >= self.max_retries:
                #     logger.info("切换到轮询模式")
                #     self._run_polling_mode()
                #     # 轮询后尝试切回 IDLE
                #     retry_count = 0
                
                if self._run_polling_mode_safe():
                    logger.info("轮询 模式启动成功,") 


                # if self._try_idle_mode():
                #     logger.info("IDLE 模式启动成功")
                #     retry_count = 0  # 成功则重置重试计数
                #     self.mode = ListenerMode.IDLE
                # else:
                #     retry_count += 1
                #     self._run_polling_mode_safe()
                #     logger.warning(f"IDLE 模式失败，尝试轮询模式 ({retry_count}/{self.max_retries})")
                #     print(f"IDLE 模式失败，尝试轮询模式 ({retry_count}/{self.max_retries})")
                #     self.mode = ListenerMode.POLLING
                #     self._stats['mode_switches'] += 1

            except Exception as e:
                last_exception = e
                logger.error(f"监听线程异常: {str(e)}", exc_info=True)  # 添加堆栈信息
                retry_count += 1
                time.sleep(5)  # 异常后等待5秒

        logger.info(f"监听线程已退出，最后异常: {last_exception}")

    def _try_idle_mode(self) -> bool:
        """
        尝试使用 IMAP IDLE 模式监听新邮件

        Returns:
            bool: 是否成功启动 IDLE 模式

        备注：此模式不稳定，暂不启用
        """
        imap = None
        try:
            # 1. 创建独立连接（不使用 connection 属性，避免自动重连）
            logger.info("IDLE 模式创建独立连接...")
            imap_config = self._imap_client.imap_config
            imap = imaplib.IMAP4_SSL(
                imap_config['imap_server'],
                imap_config['imap_port']
            )
            imap.login(imap_config['email'], imap_config['auth_code'])
            logger.info("IDLE 连接登录成功")

            # 选择文件夹
            status, _ = imap.select(self.folder)
            if status != 'OK':
                logger.error(f"IDLE 模式选择文件夹失败: {self.folder}")
                return False

            # 2. 检查能力
            _, caps = imap.capability()
            if b'IDLE' not in caps[0]:
                logger.warning("服务器不支持 IDLE")
                return False

            logger.info("服务器支持 IDLE 模式")

            # 3. 发送 IDLE 命令
            tag = imap._new_tag().decode()
            imap.send(f'{tag} IDLE\r\n'.encode())

            # 等待确认响应: 必须收到以 '+' 开头的响应才代表进入 IDLE 状态
            imap.sock.settimeout(10)  # 设置较短的超时等待确认
            initial_resp = imap.readline()
            if not initial_resp or not initial_resp.startswith(b'+'):
                logger.error(f"未能进入 IDLE 状态: {initial_resp}")
                return False

            logger.info("成功进入 IMAP IDLE 实时模式")
            self.mode = ListenerMode.IDLE

            # IDLE 主循环
            idle_count = 0
            need_reconnect = False

            while self._running and not need_reconnect:
                try:
                    # 设置超时时间（10秒心跳，更激进地维持连接）
                    imap.sock.settimeout(10)

                    line = imap.readline()
                    if not line:
                        logger.warning("IDLE 连接已被服务器关闭")
                        need_reconnect = True
                        break

                    line_str = line.decode('utf-8', errors='ignore')
                    logger.debug(f"IDLE 收到数据: {line_str.strip()}")

                    # 检查是否有新邮件信号
                    if b'EXISTS' in line or b'RECENT' in line:
                        logger.info(f"检测到新邮件信号: {line_str.strip()}")

                        # 必须先发送 DONE 退出 IDLE
                        try:
                            imap.send(b'DONE\r\n')
                            imap.sock.settimeout(5)
                            done_resp = imap.readline()
                            logger.debug(f"DONE 响应: {done_resp.decode('utf-8', errors='ignore').strip()}")
                        except (socket.timeout, OSError):
                            logger.warning("DONE 超时或连接异常，尝试继续处理邮件...")

                        # 同步邮件
                        new_emails = self._check_new_emails()
                        if new_emails:
                            self._process_new_emails(new_emails)
                        else:
                            logger.info("未找到新邮件（可能已被其他客户端标记为已读）")

                        # 重新进入 IDLE
                        try:
                            tag = imap._new_tag().decode()
                            imap.send(f'{tag} IDLE\r\n'.encode())
                            imap.sock.settimeout(10)
                            idle_resp = imap.readline()
                            if not idle_resp.startswith(b'+'):
                                logger.error(f"重新进入 IDLE 失败: {idle_resp}")
                                need_reconnect = True
                                break
                            logger.info("重新进入 IDLE 模式成功")
                        except (socket.timeout, OSError) as e:
                            logger.error(f"重新进入 IDLE 失败: {type(e).__name__}: {str(e)}")
                            need_reconnect = True
                            break

                except (socket.timeout, OSError):
                    # 定时心跳维持：每10秒重新建立 IDLE 连接
                    idle_count += 1
                    logger.info(f"IDLE 心跳 #{idle_count}，准备重建连接...")
                    need_reconnect = True  # 标记需要重连
                    break  # 退出当前循环，在外层重建连接

                except Exception as e:
                    logger.error(f"IDLE 循环异常: {type(e).__name__}: {str(e)}")
                    need_reconnect = True
                    break

            # 如果需要重连，返回 False 让外层循环重建 IDLE 连接
            if need_reconnect:
                logger.info("IDLE 连接需要重建")
                return False

            logger.info("IDLE 模式正常退出")
            return True

        except Exception as e:
            logger.error(f"IDLE 运行异常: {type(e).__name__}: {str(e)}", exc_info=True)
            self._stats['idle_failures'] += 1
            return False
        finally:
            # 清理连接
            if imap:
                try:
                    # 尝试发送 DONE 退出 IDLE
                    imap.send(b'DONE\r\n')
                    imap.sock.settimeout(2)
                    imap.readline()
                except:
                    pass

                try:
                    imap.close()
                    imap.logout()
                    logger.info("IDLE 连接已关闭")
                except Exception as e:
                    logger.warning(f"关闭 IDLE 连接时出错: {str(e)}")


    def _run_polling_mode_safe(self) -> None:
        """
        安全的轮询模式实现（连接复用版本）

        核心改进：
        - 复用 start() 方法中建立的 IMAP 连接
        - 异常时自动重建连接
        - 统计连接复用和重建次数
        """
        # 懒加载：如果 start() 中初始化失败或连接已断开，在这里重新建立
        if self._receive_service is None:
            self._receive_service = ReceiveEmailsService()
            self._stats['connection_restarts'] += 1
            logger.info("✓ IMAP 长连接已建立（轮询时延迟初始化）")

        try:
            # 复用现有连接查询新邮件
            result = self._receive_service.receive_unread_emails(count=10)

            if result['success']:
                self._stats['polling_count'] += 1
                self._stats['connection_reuses'] += 1

                # 过滤出真正的新邮件
                new_emails = []
                for email_msg in result['emails']:
                    if email_msg.msg_id != self._last_uid:
                        new_emails.append(email_msg)
                        logger.debug(f"轮询发现新邮件: {email_msg.msg_id}")

                if new_emails:
                    # 更新最新的邮件ID
                    self._last_uid = new_emails[0].msg_id
                    logger.info(f"轮询发现 {len(new_emails)} 封新邮件")
                    self._process_new_emails(new_emails)
                else:
                    logger.debug("轮询未发现新邮件")
            else:
                logger.warning(f"轮询获取邮件失败: {result.get('message', '未知错误')}")

            # 等待下次轮询
            for i in range(self.polling_interval):
                if not self._running:
                    break
                time.sleep(1)

        except Exception as e:
            # 连接异常时重建连接
            logger.error(f"IMAP 连接异常: {type(e).__name__}: {str(e)}")
            logger.info("准备重建 IMAP 连接...")

            # 清理旧连接
            if self._receive_service:
                try:
                    self._receive_service.client.close()
                    logger.info("旧连接已关闭")
                except Exception as close_error:
                    logger.warning(f"关闭旧连接时出错: {close_error}")

            # 重置服务实例，下次轮询时会创建新连接
            self._receive_service = None
            self._stats['connection_restarts'] += 1

            # 短暂等待后重新抛出异常，让外层循环重试
            time.sleep(2)
            raise  # 重新抛出异常，让外层处理重连

    def _check_new_emails(self) -> List[EmailMessage]:
        """
        检查新邮件

        Returns:
            List[EmailMessage]: 新邮件列表
        """
        imap = None
        try:
            # 创建独立连接用于读取邮件
            imap_config = self._imap_client.imap_config
            imap = imaplib.IMAP4_SSL(
                imap_config['imap_server'],
                imap_config['imap_port']
            )
            imap.login(imap_config['email'], imap_config['auth_code'])
            imap.select(self.folder)

            # 搜索未读邮件
            status, messages = imap.search(None, 'UNSEEN')
            if status != 'OK':
                logger.error(f"搜索未读邮件失败: {status}")
                return []

            email_ids = messages[0].split()
            logger.info(f"找到 {len(email_ids)} 封未读邮件")

            if not email_ids:
                return []

            # 解析邮件
            new_emails = []
            service = ReceiveEmailsService()

            for msg_id in reversed(email_ids[-10:]):  # 最多获取最新的10封
                try:
                    msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id

                    # 跳过已处理的邮件
                    if msg_id_str == self._last_uid:
                        logger.debug(f"跳过已处理邮件: {msg_id_str}")
                        continue

                    # 获取邮件内容
                    status, msg_data = imap.fetch(msg_id, '(RFC822)')
                    if status != 'OK':
                        logger.warning(f"获取邮件失败: {msg_id_str}")
                        continue

                    import email
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # 解析邮件
                    email_msg = service._parse_email_message(msg, msg_id_str)
                    new_emails.append(email_msg)

                    # # 标记为已读
                    # self.imap.store(self.msg_id, '+FLAGS', '\\Seen')
                    # logger.info(f"解析新邮件: {email_msg.subject} from {email_msg.from_email}")

                    # 更新最新 UID
                    self._last_uid = msg_id_str

                except Exception as e:
                    logger.error(f"解析邮件 {msg_id} 失败: {str(e)}")
                    continue

            return new_emails

        except Exception as e:
            logger.error(f"检查新邮件失败: {type(e).__name__}: {str(e)}")
            return []
        finally:
            # 关闭独立连接
            if imap:
                try:
                    imap.close()
                    imap.logout()
                except:
                    pass

    def _process_new_emails(self, emails: List[EmailMessage]) -> None:
        """
        处理新邮件（异步非阻塞版本）

        Args:
            emails: 新邮件列表
        """
        if not emails:
            return

        self._stats['total_received'] += len(emails)
        logger.info(f"收到 {len(emails)} 封新邮件")

        # 打印邮件摘要
        for email_msg in emails:
            logger.info(f"  - {email_msg.subject} ({email_msg.from_email})")

        # 先标记邮件为已读（避免重复处理）
        try:
            msg_ids_to_mark = [email_msg.msg_id for email_msg in emails]

            # 使用活跃的连接（_receive_service.client）而不是 _imap_client
            # 因为 _receive_service.client 一直在轮询，连接是活跃的
            if self._receive_service and self._receive_service.client:
                mark_result = self._receive_service.client.store_flags(
                    msg_ids=msg_ids_to_mark,
                    flag_command='+FLAGS',
                    flags='\\Seen',
                    folder=self.folder
                )
                if mark_result['success']:
                    logger.info(f"成功标记 {mark_result['count']} 封邮件为已读")
                else:
                    logger.warning(f"标记邮件为已读失败: {mark_result.get('message', '未知错误')}")
            else:
                # 降级到 _imap_client（可能需要重连）
                logger.warning("活跃连接不可用，使用备用连接标记邮件")
                mark_result = self._imap_client.store_flags(
                    msg_ids=msg_ids_to_mark,
                    flag_command='+FLAGS',
                    flags='\\Seen',
                    folder=self.folder
                )
                if mark_result['success']:
                    logger.info(f"成功标记 {mark_result['count']} 封邮件为已读")
                else:
                    logger.warning(f"标记邮件为已读失败: {mark_result.get('message', '未知错误')}")
        except Exception as e:
            logger.error(f"标记邮件为已读时出错: {str(e)}")

        # 提交到线程池异步处理（非阻塞）
        if self._executor:
            future = self._executor.submit(self._execute_callback, emails)
            self._pending_futures.append(future)

            # 添加回调函数，处理完成和异常
            future.add_done_callback(self._on_task_complete)

            # 更新统计
            self._stats['processing_tasks'] = len(self._pending_futures)

            logger.info(f"邮件已提交到线程池处理，当前待处理任务: {self._stats['processing_tasks']}")
        else:
            logger.error("线程池未初始化，无法处理邮件")

    def _execute_callback(self, emails: List[EmailMessage]) -> None:
        """
        执行回调函数（在工作线程中运行）

        Args:
            emails: 新邮件列表
        """
        try:
            self.new_email_callback(emails)
            logger.info(f"✓ 成功处理 {len(emails)} 封新邮件")
        except Exception as e:
            logger.error(f"执行邮件回调失败: {str(e)}", exc_info=True)

    def _on_task_complete(self, future: Future) -> None:
        """
        任务完成回调（在主线程中运行）

        Args:
            future: 已完成的 Future 对象
        """
        # 从待处理列表中移除
        if future in self._pending_futures:
            self._pending_futures.remove(future)

        # 更新统计
        self._stats['processing_tasks'] = len(self._pending_futures)
        self._stats['completed_tasks'] += 1

        # 检查是否有异常
        if future.exception():
            logger.error(f"邮件处理任务异常: {future.exception()}")

        logger.debug(
            f"任务完成，当前待处理: {self._stats['processing_tasks']}, "
            f"已完成: {self._stats['completed_tasks']}"
        )

    def get_status(self) -> Dict[str, Any]:
        """
        获取监听服务状态

        Returns:
            Dict: 状态信息
        """
        return {
            'running': self._running,
            'mode': self.mode.value,
            'folder': self.folder,
            'last_uid': self._last_uid,
            'thread_alive': self._thread.is_alive() if self._thread else False,
            'stats': self._stats.copy(),
            # 线程池状态
            'thread_pool': {
                'max_workers': self.max_workers,
                'active_tasks': self._stats['processing_tasks'],
                'completed_tasks': self._stats['completed_tasks']
            } if self._executor else None,
            # 连接复用状态（新增）
            'connection': {
                'is_established': self._receive_service is not None,
                'reuses': self._stats.get('connection_reuses', 0),
                'restarts': self._stats.get('connection_restarts', 0),
                'reuse_rate': f"{(self._stats.get('connection_reuses', 0) / max(self._stats.get('polling_count', 1), 1) * 100):.1f}%"
            }
        }

    def switch_mode(self, mode: ListenerMode) -> bool:
        """
        手动切换监听模式

        Args:
            mode: 目标模式

        Returns:
            bool: 是否切换成功
        """
        if mode == ListenerMode.IDLE:
            logger.info("手动切换到 IDLE 模式")
            # 重置重试计数，允许下次循环尝试 IDLE
            return True
        elif mode == ListenerMode.POLLING:
            logger.info("手动切换到轮询模式")
            self.mode = ListenerMode.POLLING
            self._stats['mode_switches'] += 1
            return True
        else:
            return False


# 创建全局监听器实例（延迟初始化）
_global_listener: Optional[EmailListener] = None


def start_email_listener(
    new_email_callback: Callable[[List[EmailMessage]], None],
    polling_interval: int = 60,
    idle_timeout: int = 290,
    folder: str = 'INBOX',
    initial_sync_count: int = 30,
    max_workers: int = 3
) -> EmailListener:
    """
    启动邮件监听服务（全局实例）

    Args:
        new_email_callback: 新邮件回调函数
        polling_interval: 轮询间隔（秒）
        idle_timeout: IDLE超时时间（秒）
        folder: 监听的邮箱文件夹
        initial_sync_count: 启动时同步的最近邮件数量
        max_workers: 线程池最大工作线程数，默认3个

    Returns:
        EmailListener: 监听器实例
    """
    global _global_listener

    # 如果已有实例，先停止
    if _global_listener and _global_listener._running:
        _global_listener.stop()

    # 创建新实例
    _global_listener = EmailListener(
        new_email_callback=new_email_callback,
        polling_interval=polling_interval,
        idle_timeout=idle_timeout,
        folder=folder,
        max_workers=max_workers
    )

    _global_listener.start(initial_sync_count=initial_sync_count)
    return _global_listener


def stop_email_listener() -> None:
    """停止邮件监听服务（全局实例）"""
    global _global_listener

    if _global_listener:
        _global_listener.stop()


def get_listener_status() -> Dict[str, Any]:
    """获取邮件监听服务状态（全局实例）"""
    global _global_listener

    if _global_listener:
        return _global_listener.get_status()
    else:
        return {'running': False, 'mode': 'stopped'}


if __name__ == "__main__":
    """测试代码"""

    def on_new_email(emails):
        print(f"\n🔔 收到 {len(emails)} 封新邮件！")
        for email_msg in emails:
            print(f"  主题: {email_msg.subject}")
            print(f"  发件人: {email_msg.from_email}")
            print(f"  日期: {email_msg.date}")
            print()

    print("=== 测试邮件监听服务 ===\n")

    # 启动监听
    listener = start_email_listener(
        new_email_callback=on_new_email,
        polling_interval=30,  # 测试用30秒
        folder='INBOX'
    )

    print("监听服务已启动，等待新邮件...")
    print("按 Ctrl+C 退出\n")

    try:
        # 定期打印状态
        while True:
            time.sleep(10)
            status = listener.get_status()
            print(f"状态: {status['mode']}, 已收: {status['stats']['total_received']} 封")

    except KeyboardInterrupt:
        print("\n\n正在停止监听服务...")
        stop_email_listener()
        print("监听服务已停止")
