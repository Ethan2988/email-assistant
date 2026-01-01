import threading
import time
import logging
import socket
import imaplib
import select
from typing import Callable, Dict, Any, List, Optional
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass

# 假设这些类在你的项目中已定义，此处保持导入路径
from .receive_emails_service import EmailMessage, ReceiveEmailsService
from .email_client import IMAPClient

# 配置日志
logger = logging.getLogger(__name__)

class IdleState(Enum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    IDLE = "idle"             # 正在实时监听
    PROCESSING = "processing" # 正在抓取/处理邮件
    ERROR = "error"

@dataclass
class IdleConfig:
    folder: str = 'INBOX'
    heartbeat_interval: int = 120      # QQ邮箱建议 120-180秒
    max_retries: int = 5
    retry_delay: int = 5
    max_workers: int = 3
    initial_sync_count: int = 10
    debug_mode: bool = True            # 建议开启以观察原始信号

class EmailListenerIdle:
    """
    架构优化版：基于 IMAP IDLE 的实时监听服务
    解决了 SSL 缓冲区残留信号丢失以及 Socket 超时导致的连接损毁问题
    """

    def __init__(
        self,
        new_email_callback: Callable[[List[EmailMessage]], None],
        imap_client: Optional[IMAPClient] = None,
        config: Optional[IdleConfig] = None
    ):
        self.new_email_callback = new_email_callback
        self.config = config or IdleConfig()
        self._imap_client = imap_client if imap_client else IMAPClient()
        
        self._idle_conn: Optional[imaplib.IMAP4_SSL] = None
        self._receive_service = ReceiveEmailsService()
        
        self.state = IdleState.STOPPED
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._processed_uids: set = set()
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        self._pending_futures: List[Future] = []

    def start(self, initial_sync: bool = True) -> bool:
        if self._running: return False
        
        logger.info("正在启动 IDLE 监听服务...")
        self._running = True
        self._stop_event.clear()

        if initial_sync:
            self._initial_sync()

        self._thread = threading.Thread(target=self._run_loop, name="IdleThread", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        self._stop_event.set()
        self._close_connection()
        if self._executor:
            self._executor.shutdown(wait=False)
        logger.info("IDLE 监听服务已指令停止")

    def _run_loop(self):
        """主监听循环"""
        while self._running:
            try:
                if not self._establish_connection():
                    time.sleep(self.config.retry_delay)
                    continue

                while self._running:
                    # 1. 进入 IDLE 模式
                    if not self._enter_idle_mode():
                        break

                    # 2. 阻塞等待信号
                    self.state = IdleState.IDLE
                    has_signal = self._wait_for_signal(timeout=self.config.heartbeat_interval)

                    # 3. 退出 IDLE 模式以进行后续操作
                    self.state = IdleState.PROCESSING
                    self._exit_idle_mode()

                    # 4. 如果有信号，抓取邮件
                    if has_signal:
                        self._handle_new_emails()
                    
                    # 检查是否需要重建连接（心跳保活）
                    # 正常循环会自动进入下一次 IDLE

            except Exception as e:
                logger.error(f"监听循环异常: {e}", exc_info=True)
                self._close_connection()
                time.sleep(self.config.retry_delay)

    def _establish_connection(self) -> bool:
        """建立并初始化 IMAP 连接"""
        try:
            self._close_connection()
            conf = self._imap_client.imap_config
            self._idle_conn = imaplib.IMAP4_SSL(conf['imap_server'], conf['imap_port'])
            self._idle_conn.login(conf['email'], conf['auth_code'])
            self._idle_conn.select(self.config.folder)
            
            # 确认支持 IDLE
            _, caps = self._idle_conn.capability()
            if b'IDLE' not in caps[0]:
                logger.error("服务器不支持 IDLE")
                return False
            
            logger.info(f"✓ IDLE 连接已就绪: {conf['email']}")
            return True
        except Exception as e:
            logger.error(f"建立连接失败: {e}")
            return False

    def _enter_idle_mode(self) -> bool:
        """发送 IDLE 命令"""
        try:
            # 清空 Socket 现有缓冲区
            self._idle_conn.sock.setblocking(False)
            try:
                while self._idle_conn.sock.recv(4096): pass
            except: pass
            self._idle_conn.sock.setblocking(True)

            # 发送 IDLE
            tag = self._idle_conn._new_tag().decode()
            self._idle_conn.send(f'{tag} IDLE\r\n'.encode())
            
            # 等待 "+" 确认
            resp = self._idle_conn.readline()
            if resp and resp.startswith(b'+'):
                if self.config.debug_mode: logger.debug("IDLE 模式激活成功")
                return True
            return False
        except Exception as e:
            logger.error(f"进入 IDLE 失败: {e}")
            return False

    def _wait_for_signal(self, timeout: int) -> bool:
        """
        核心监控逻辑：双重探测机制
        同时监控系统 Socket 和 SSL 内存缓冲区
        """
        sock = self._idle_conn.sock
        start_time = time.time()

        while self._running and (time.time() - start_time < timeout):
            # A. 预检：SSL 内存缓冲区探测（解决信号卡在内存的问题）
            sock.setblocking(False)
            try:
                line = self._idle_conn.readline()
                if line and self._is_new_mail_signal(line):
                    return True
            except:
                pass # 缓冲区无完整行
            finally:
                sock.setblocking(True)

            # B. 阻塞：Select 监控系统 Socket
            remaining = max(0, timeout - (time.time() - start_time))
            if remaining <= 0: break
            
            r, _, _ = select.select([sock], [], [], remaining)
            if r:
                try:
                    line = self._idle_conn.readline()
                    if not line: return False # 连接断开
                    if self._is_new_mail_signal(line):
                        return True
                except Exception as e:
                    logger.error(f"读取数据流异常: {e}")
                    return False
            else:
                return False # 自然超时（心跳）
        return False

    def _is_new_mail_signal(self, line: bytes) -> bool:
        """信号解析逻辑"""
        line_str = line.decode('utf-8', errors='ignore').upper()
        if self.config.debug_mode:
            logger.debug(f"RAW: {line_str.strip()}")
        
        # EXISTS 代表邮件数量变化，这是最可靠的信号
        if 'EXISTS' in line_str or 'RECENT' in line_str:
            logger.info(f"🔔 捕获到新邮件信号: {line_str.strip()}")
            return True
        return False

    def _exit_idle_mode(self):
        """安全退出 IDLE"""
        try:
            self._idle_conn.send(b'DONE\r\n')
            self._idle_conn.sock.settimeout(2)
            self._idle_conn.readline()
        except:
            pass

    def _handle_new_emails(self):
        """获取并处理新邮件"""
        try:
            # 复用当前连接进行搜索，无需新建连接，效率最高
            typ, data = self._idle_conn.uid('search', None, 'UNSEEN')
            if typ != 'OK': return
            
            new_uids = data[0].split()
            emails_to_process = []
            
            for uid in new_uids:
                uid_str = uid.decode()
                if uid_str not in self._processed_uids:
                    # 使用 receive_service 解析具体邮件内容
                    # 注意：此处建议在 ReceiveEmailsService 中增加一个支持传入 client 的方法
                    res = self._receive_service.receive_single_email_by_uid(uid_str, client=self._idle_conn)
                    if res:
                        emails_to_process.append(res)
                        self._processed_uids.add(uid_str)

            if emails_to_process:
                self._executor.submit(self.new_email_callback, emails_to_process)
                
            # 保持集合大小，防止内存溢出
            if len(self._processed_uids) > 1000:
                self._processed_uids = set(list(self._processed_uids)[-500:])

        except Exception as e:
            logger.error(f"提取新邮件内容失败: {e}")

    def _close_connection(self):
        if self._idle_conn:
            try:
                self._idle_conn.logout()
            except:
                pass
            self._idle_conn = None

    def _initial_sync(self):
        """启动时的初始同步"""
        logger.info("执行启动同步...")
        try:
            res = self._receive_service.receive_unread_emails(count=self.config.initial_sync_count)
            if res['success']:
                for m in res['emails']:
                    self._processed_uids.add(str(m.msg_id))
                logger.info(f"初始同步完成，已忽略 {len(res['emails'])} 封旧邮件")
        except Exception as e:
            logger.error(f"初始同步异常: {e}")