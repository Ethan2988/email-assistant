"""
Email Assistant 主入口

"""

import os
import signal
import sys
import time
import threading
from .tools import Email_tool
from .service.scheduler_service import scheduler_service
from .service.task_manager import get_task_manager
from .service import (
    start_email_listener,
    stop_email_listener,
    get_listener_status,
    EmailMessage,
    EmailListenerIdle

)
from .agents import EmailAgent

# ⭐ 已处理邮件的缓存（防止重复处理）
_processed_emails = set()
_processed_emails_lock = threading.Lock()  # 线程安全锁

from .config import EmailConfig



def service_online()->None:
    config = EmailConfig()

    subject = 'Email assistant online'
    content = "hi，邮件助手已上线，有什么需要我来帮你处理的吗？"
    sender_name = "Email Assistant"
    to_emails = config.get_master_info().get('master_email')

    print(to_emails)

    result = Email_tool().send_email_simple.func(to_emails,subject,content,sender_name)

    print(result)


def signal_handler(sig, frame):
    """处理退出信号（Ctrl+C 或 kill 信号）"""
    print("\n\n收到退出信号，正在优雅关闭...")
    stop_all_services()
    print("👋 程序已安全退出，再见！")
    sys.exit(0)

def stop_all_services() -> None:
    """
    优雅地停止所有服务（带异常处理和状态检查）

    停止顺序：
    1. 邮件监听器（等待线程池任务完成，最多30秒）
    2. 调度器（等待任务完成）
    """
    errors = []

    # 1. 停止邮件监听器
    try:
        print("\n📧 正在停止邮件监听器...")

        status = get_listener_status()

        if status.get('running'):
            # 检查是否有正在处理的任务
            thread_pool = status.get('thread_pool')
            if thread_pool and thread_pool.get('active_tasks', 0) > 0:
                print(f"⏳ 等待 {thread_pool['active_tasks']} 个邮件处理任务完成...")

            stop_email_listener()
            print("✓ 邮件监听器已停止")
        else:
            print("ℹ️  邮件监听器未运行，跳过")

    except Exception as e:
        error_msg = f"停止邮件监听器失败: {str(e)}"
        print(f"❌ {error_msg}")
        errors.append(error_msg)

    # 2. 停止调度器
    try:
        print("\n⏰ 正在停止调度器...")
        scheduler_service.stop()
        print("✓ 调度器已停止")
    except Exception as e:
        error_msg = f"停止调度器失败: {str(e)}"
        print(f"❌ {error_msg}")
        errors.append(error_msg)

    # 报告错误汇总
    if errors:
        print(f"\n⚠️  停止过程中发生 {len(errors)} 个错误:")
        for i, error in enumerate(errors, 1):
            print(f"    {i}. {error}")

    print("\n" + "="*50)
    print("所有服务已关闭")
    print("="*50)


def scheduler_service_start() -> None:
    # 启动调度器
    print("正在启动调度器...")
    scheduler_service.start()
    print("调度器已启动")

    task_manager = get_task_manager()

    # 从数据库加载任务到调度器（先加载已存在的任务）
    print("正在从数据库加载任务...")

    load_result = task_manager.load_tasks_from_db()
    print(f"{load_result['message']}")

    if load_result.get('failed_tasks'):
        print(f"⚠️  {len(load_result['failed_tasks'])} 个任务加载失败:")
        for failed in load_result['failed_tasks']:
            print(f"    - {failed['task_id']}: {failed['error']}") 




def on_new_email(emails: list[EmailMessage]) -> None:
    """
    新邮件回调函数（防重复处理版本，线程安全）

    Args:
        emails: 新邮件列表
    """
    global _processed_emails

    print(f"\n🔔 收到 {len(emails)} 封新邮件！")

    agent = EmailAgent()

    for email_msg in emails:
        # ⭐ 步骤1：检查是否已处理（防止重复处理）- 使用线程锁
        email_id = email_msg.msg_id

        with _processed_emails_lock:
            if email_id in _processed_emails:
                print(f"⚠️ 邮件已处理，跳过: {email_msg.subject}")
                continue

            # ⭐ 步骤2：标记为已处理
            _processed_emails.add(email_id)

            # ⭐ 步骤3：限制缓存大小（防止内存泄漏）
            if len(_processed_emails) > 1000:
                # 清除最旧的500条记录
                old_ids = list(_processed_emails)[:500]
                _processed_emails.difference_update(old_ids)
                print(f"📝 清理已处理邮件缓存，当前缓存: {len(_processed_emails)} 条")

        print(f"  ┌─ 主题: {email_msg.subject}")
        print(f"  │  发件人: {email_msg.from_name} <{email_msg.from_email}>")
        print(f"  │  日期: {email_msg.date}")
        if email_msg.attachments:
            print(f"  │  附件: {len(email_msg.attachments)} 个")
            for att in email_msg.attachments:
                print(f"  │    - {att['filename']}")
        print(f"  └─ 正文长度: {len(email_msg.body)} 字符")

        print("大模型正在处理邮件...")
        agent.run(email_msg)

        print(f"✓ 邮件处理完成: subject{email_msg.subject}")

def idle_listener() -> None:
    # 开启IDEL协议的邮件监听器
    EmailListenerIdle(on_new_email).start()


def polling_listener() -> None:
    # 开启轮询模式的监听器
    start_email_listener(
        new_email_callback=on_new_email,
        polling_interval=60,       # 轮询间隔60秒
        folder='INBOX',            # 监听收件箱
        initial_sync_count=30      # 启动时同步最近30封邮件
    )
    print("轮询模式邮件监听器已启动）")


def system_init() -> None:
    """
    系统初始化

    执行步骤：
    1. 发送上线通知
    2. 启动调度器并加载定时任务
    3. 启动邮件监听器
    4. 注册信号处理器（优雅关闭）
    """
    # 发送上线通知
    service_online()

    # 启动调度器，加载定时任务
    scheduler_service_start()

    # 启动邮件监听器
    print("正在启动邮件监听器...")
    polling_listener()

    # 注册信号处理器（Ctrl+C 和 kill 命令）
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill 命令
    print("✓ 已注册信号处理器（支持 Ctrl+C 优雅关闭）")


def stop_run() -> None:
    """
    主动停止所有服务（用户手动调用）

    与 signal_handler 的区别：
    - signal_handler: 处理系统信号（Ctrl+C、kill）
    - stop_run: 用户主动调用停止

    两者都调用 stop_all_services() 执行实际的停止逻辑
    """
    print("\n正在停止所有服务...")
    stop_all_services()
    print("\n👋 已手动停止程序，再见！")
    sys.exit(0)