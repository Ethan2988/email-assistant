"""
定时器服务
支持多种类型的定时任务，在独立线程中执行邮件发送等任务
"""

import logging
import threading
from datetime import datetime, time
from typing import Callable, Dict, Any, Optional, List, Union
from enum import Enum
from pathlib import Path

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.jobstores.memory import MemoryJobStore
    from apscheduler.executors.pool import ThreadPoolExecutor
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    BackgroundScheduler = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    """定时器类型枚举"""
    ONCE = "once"              # 一次性任务，指定具体时间
    DAILY = "daily"            # 每天定时执行
    WEEKLY = "weekly"          # 每周定时执行
    INTERVAL = "interval"      # 间隔时间执行
    CRON = "cron"              # Cron表达式


class EmailTask:
    """邮件任务类"""

    def __init__(
        self,
        task_id: str,
        recipients: Union[str, List[str]],
        subject: str,
        content: str,
        content_type: str = 'plain',
        cc_emails: Union[str, List[str]] = None,
        bcc_emails: Union[str, List[str]] = None,
        attachment_paths: List[str] = None,
        sender_name: str = None
    ):
        self.task_id = task_id
        self.recipients = recipients
        self.subject = subject
        self.content = content
        self.content_type = content_type
        self.cc_emails = cc_emails
        self.bcc_emails = bcc_emails
        self.attachment_paths = attachment_paths
        self.sender_name = sender_name

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'recipients': self.recipients,
            'subject': self.subject,
            'content': self.content,
            'content_type': self.content_type,
            'cc_emails': self.cc_emails,
            'bcc_emails': self.bcc_emails,
            'attachment_paths': self.attachment_paths,
            'sender_name': self.sender_name
        }


class SchedulerService:
    """
    定时器服务

    支持多种定时任务类型：
    - 一次性任务：指定具体时间执行一次
    - 每天任务：每天指定时间执行
    - 每周任务：每周指定星期和时间执行
    - 间隔任务：按时间间隔执行
    - Cron任务：使用Cron表达式
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: int = 10):
        """
        初始化定时器服务

        Args:
            max_workers: 最大工作线程数
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        if not APSCHEDULER_AVAILABLE:
            raise ImportError(
                "需要安装 APScheduler 库。请运行: pip install apscheduler"
            )

        self.max_workers = max_workers
        self.scheduler = None
        self.email_service = None
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        self._running = False

        # 延迟导入，避免循环导入
        from .send_email_service import QQEmailService
        self.email_service = QQEmailService()

    def initialize(self) -> None:
        """初始化调度器"""
        if self._initialized:
            return

        try:
            # 配置调度器
            jobstores = {
                'default': MemoryJobStore()
            }
            executors = {
                'default': ThreadPoolExecutor(max_workers=self.max_workers)
            }
            job_defaults = {
                'coalesce': True,        # 合并多个待执行的相同任务
                'max_instances': 1,      # 同一任务最多同时运行1个实例
                'misfire_grace_time': 60  # 错过执行时间的宽限时间（秒）
            }

            self.scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='Asia/Shanghai'
            )

            logger.info("定时器服务初始化成功")
            self._initialized = True

        except Exception as e:
            logger.error(f"定时器服务初始化失败: {str(e)}")
            raise

    def start(self) -> None:
        """启动定时器服务"""
        if not self._initialized:
            self.initialize()

        if not self._running:
            self.scheduler.start()
            self._running = True
            logger.info("定时器服务已启动")

    def stop(self) -> None:
        """停止定时器服务"""
        if self._running and self.scheduler:
            self.scheduler.shutdown(wait=True)
            self._running = False
            logger.info("定时器服务已停止")

    def pause_job(self, job_id: str) -> bool:
        """暂停指定任务"""
        try:
            if self.scheduler:
                self.scheduler.pause_job(job_id)
                logger.info(f"任务已暂停: {job_id}")
                return True
        except Exception as e:
            logger.error(f"暂停任务失败: {str(e)}")
        return False

    def resume_job(self, job_id: str) -> bool:
        """恢复指定任务"""
        try:
            if self.scheduler:
                self.scheduler.resume_job(job_id)
                logger.info(f"任务已恢复: {job_id}")
                return True
        except Exception as e:
            logger.error(f"恢复任务失败: {str(e)}")
        return False

    def remove_job(self, job_id: str) -> bool:
        """移除指定任务"""
        try:
            if self.scheduler:
                self.scheduler.remove_job(job_id)
                if job_id in self.tasks:
                    del self.tasks[job_id]
                logger.info(f"任务已移除: {job_id}")
                return True
        except Exception as e:
            logger.error(f"移除任务失败: {str(e)}")
        return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        jobs = []
        if self.scheduler:
            for job in self.scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                })
        return jobs

    def get_task_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        return self.tasks.get(job_id)

    # ==================== 一次性任务 ====================

    def schedule_once(
        self,
        task_id: str,
        run_date: Union[datetime, str],
        task: Union[EmailTask, Callable],
        callback: Optional[Callable] = None
    ) -> bool:
        """
        安排一次性任务

        Args:
            task_id: 任务ID
            run_date: 执行时间，datetime对象或"YYYY-MM-DD HH:MM:SS"格式字符串
            task: 邮件任务对象或可执行函数
            callback: 执行完成后的回调函数

        Returns:
            bool: 是否添加成功

        Example:
            # 方式1：使用datetime对象
            schedule_once(
                "task_1",
                datetime(2025, 12, 30, 12, 0),
                email_task
            )

            # 方式2：使用字符串
            schedule_once(
                "task_2",
                "2025-12-30 12:00:00",
                email_task
            )
        """
        try:
            if isinstance(run_date, str):
                run_date = datetime.strptime(run_date, "%Y-%m-%d %H:%M:%S")

            job = self.scheduler.add_job(
                func=self._execute_task,
                trigger=DateTrigger(run_date=run_date, timezone='Asia/Shanghai'),
                id=task_id,
                args=[task, callback],
                name=f"一次性任务-{task_id}"
            )

            self._register_task(task_id, ScheduleType.ONCE, job, task)
            logger.info(f"一次性任务已添加: {task_id}, 执行时间: {run_date}")
            return True

        except Exception as e:
            logger.error(f"添加一次性任务失败: {str(e)}")
            return False

    # ==================== 每天定时任务 ====================

    def schedule_daily(
        self,
        task_id: str,
        run_time: Union[time, str],
        task: Union[EmailTask, Callable],
        callback: Optional[Callable] = None
    ) -> bool:
        """
        安排每天定时任务

        Args:
            task_id: 任务ID
            run_time: 执行时间，time对象或"HH:MM"格式字符串
            task: 邮件任务对象或可执行函数
            callback: 执行完成后的回调函数

        Returns:
            bool: 是否添加成功

        Example:
            # 方式1：使用time对象
            schedule_daily("daily_noon", time(12, 0), email_task)

            # 方式2：使用字符串
            schedule_daily("daily_afternoon", "17:00", email_task)
        """
        try:
            if isinstance(run_time, str):
                hour, minute = map(int, run_time.split(':'))
                run_time = time(hour=hour, minute=minute)

            job = self.scheduler.add_job(
                func=self._execute_task,
                trigger=CronTrigger(
                    hour=run_time.hour,
                    minute=run_time.minute,
                    timezone='Asia/Shanghai'
                ),
                id=task_id,
                args=[task, callback],
                name=f"每天定时任务-{task_id}"
            )

            self._register_task(task_id, ScheduleType.DAILY, job, task)
            logger.info(f"每天定时任务已添加: {task_id}, 执行时间: {run_time}")
            return True

        except Exception as e:
            logger.error(f"添加每天定时任务失败: {str(e)}")
            return False

    # ==================== 每周定时任务 ====================

    def schedule_weekly(
        self,
        task_id: str,
        day_of_week: int,
        run_time: Union[time, str],
        task: Union[EmailTask, Callable],
        callback: Optional[Callable] = None
    ) -> bool:
        """
        安排每周定时任务

        Args:
            task_id: 任务ID
            day_of_week: 星期几，0=周一, 6=周日
            run_time: 执行时间，time对象或"HH:MM"格式字符串
            task: 邮件任务对象或可执行函数
            callback: 执行完成后的回调函数

        Returns:
            bool: 是否添加成功

        Example:
            # 每周一中午12点执行
            schedule_weekly("weekly_monday", 0, "12:00", email_task)

            # 每周五下午5点执行
            schedule_weekly("weekly_friday", 4, time(17, 0), email_task)
        """
        try:
            if isinstance(run_time, str):
                hour, minute = map(int, run_time.split(':'))
                run_time = time(hour=hour, minute=minute)

            job = self.scheduler.add_job(
                func=self._execute_task,
                trigger=CronTrigger(
                    day_of_week=day_of_week,
                    hour=run_time.hour,
                    minute=run_time.minute,
                    timezone='Asia/Shanghai'
                ),
                id=task_id,
                args=[task, callback],
                name=f"每周定时任务-{task_id}"
            )

            self._register_task(task_id, ScheduleType.WEEKLY, job, task)
            logger.info(f"每周定时任务已添加: {task_id}, 星期{day_of_week}, 时间: {run_time}")
            return True

        except Exception as e:
            logger.error(f"添加每周定时任务失败: {str(e)}")
            return False

    # ==================== 间隔任务 ====================

    def schedule_interval(
        self,
        task_id: str,
        interval_seconds: int,
        task: Union[EmailTask, Callable],
        callback: Optional[Callable] = None,
        start_date: Optional[Union[datetime, str]] = None
    ) -> bool:
        """
        安排间隔执行任务

        Args:
            task_id: 任务ID
            interval_seconds: 间隔秒数
            task: 邮件任务对象或可执行函数
            callback: 执行完成后的回调函数
            start_date: 开始时间，可选

        Returns:
            bool: 是否添加成功

        Example:
            # 每小时执行一次
            schedule_interval("hourly", 3600, email_task)

            # 每30分钟执行一次
            schedule_interval("half_hour", 1800, email_task)
        """
        try:
            trigger_kwargs = {'seconds': interval_seconds}
            if start_date:
                if isinstance(start_date, str):
                    start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
                trigger_kwargs['start_date'] = start_date

            job = self.scheduler.add_job(
                func=self._execute_task,
                trigger=IntervalTrigger(
                    **trigger_kwargs,
                    timezone='Asia/Shanghai'
                ),
                id=task_id,
                args=[task, callback],
                name=f"间隔任务-{task_id}"
            )

            self._register_task(task_id, ScheduleType.INTERVAL, job, task)
            logger.info(f"间隔任务已添加: {task_id}, 间隔: {interval_seconds}秒")
            return True

        except Exception as e:
            logger.error(f"添加间隔任务失败: {str(e)}")
            return False

    # ==================== Cron表达式任务 ====================

    def schedule_cron(
        self,
        task_id: str,
        cron_expression: str,
        task: Union[EmailTask, Callable],
        callback: Optional[Callable] = None
    ) -> bool:
        """
        使用Cron表达式安排任务

        Args:
            task_id: 任务ID
            cron_expression: Cron表达式，格式: 分 时 日 月 周
            task: 邮件任务对象或可执行函数
            callback: 执行完成后的回调函数

        Returns:
            bool: 是否添加成功

        Example:
            # 每天凌晨2点执行
            schedule_cron("daily_midnight", "0 2 * * *", email_task)

            # 每月1号上午10点执行
            schedule_cron("monthly", "0 10 1 * *", email_task)

            # 工作日上午9点执行（周一到周五）
            schedule_cron("workday_morning", "0 9 * * 1-5", email_task)
        """
        try:
            parts = cron_expression.split()
            if len(parts) != 5:
                raise ValueError("Cron表达式格式错误，应为: 分 时 日 月 周")

            minute, hour, day, month, day_of_week = parts

            job = self.scheduler.add_job(
                func=self._execute_task,
                trigger=CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone='Asia/Shanghai'
                ),
                id=task_id,
                args=[task, callback],
                name=f"Cron任务-{task_id}"
            )

            self._register_task(task_id, ScheduleType.CRON, job, task)
            logger.info(f"Cron任务已添加: {task_id}, 表达式: {cron_expression}")
            return True

        except Exception as e:
            logger.error(f"添加Cron任务失败: {str(e)}")
            return False

    # ==================== 辅助方法 ====================

    def _register_task(
        self,
        job_id: str,
        schedule_type: ScheduleType,
        job,
        task: Union[EmailTask, Callable]
    ) -> None:
        """注册任务信息"""
        self.tasks[job_id] = {
            'job_id': job_id,
            'schedule_type': schedule_type,
            'job': job,
            'task': task,
            'created_at': datetime.now()
        }

    def _execute_task(
        self,
        task: Union[EmailTask, Callable],
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        执行任务

        Args:
            task: 邮件任务对象或可执行函数
            callback: 回调函数

        Returns:
            Dict: 执行结果
        """
        result = {'success': False, 'message': '', 'data': None}

        try:
            if isinstance(task, EmailTask):
                # 执行邮件任务
                logger.info(f"开始执行邮件任务: {task.task_id}")
                result = self.email_service.send_email(
                    to_emails=task.recipients,
                    subject=task.subject,
                    content=task.content,
                    content_type=task.content_type,
                    cc_emails=task.cc_emails,
                    bcc_emails=task.bcc_emails,
                    attachment_paths=task.attachment_paths,
                    sender_name=task.sender_name
                )

                if result['success']:
                    logger.info(f"邮件任务执行成功: {task.task_id}")
                else:
                    logger.error(f"邮件任务执行失败: {task.task_id}, 错误: {result.get('message')}")

            elif callable(task):
                # 执行自定义函数
                logger.info("开始执行自定义任务")
                result = task()
                result = {'success': True, 'message': '任务执行完成', 'data': result}
                logger.info("自定义任务执行完成")

            # 执行回调
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"回调函数执行失败: {str(e)}")

        except Exception as e:
            logger.error(f"任务执行异常: {str(e)}")
            result = {
                'success': False,
                'message': f'任务执行异常: {str(e)}',
                'data': None
            }

        return result

    def is_running(self) -> bool:
        """检查调度器是否正在运行"""
        return self._running and self.scheduler and self.scheduler.running

    def get_next_run_time(self, job_id: str) -> Optional[datetime]:
        """获取任务下次执行时间"""
        try:
            if self.scheduler:
                job = self.scheduler.get_job(job_id)
                if job:
                    return job.next_run_time
        except Exception as e:
            logger.error(f"获取任务下次执行时间失败: {str(e)}")
        return None


# 创建全局实例
scheduler_service = SchedulerService()


if __name__ == "__main__":
    """测试代码"""

    # 测试定时器服务
    print("=== 测试定时器服务 ===\n")

    # 创建调度器实例
    service = SchedulerService()

    # 启动服务
    service.start()

    # 创建邮件任务
    email_task = EmailTask(
        task_id="test_email",
        recipients="990151152@qq.com",
        subject="定时器测试邮件",
        content="这是一封由定时器服务自动发送的测试邮件"
    )

    # 示例1：添加一次性任务（1分钟后执行）
    from datetime import datetime, timedelta
    test_time = datetime.now() + timedelta(minutes=1)
    service.schedule_once(
        task_id="once_test",
        run_date=test_time,
        task=email_task
    )
    print(f"已添加一次性任务，将在 {test_time.strftime('%Y-%m-%d %H:%M:%S')} 执行")

    # 示例2：添加每天定时任务（测试用，实际时间请在使用时修改）
    # service.schedule_daily(
    #     task_id="daily_noon",
    #     run_time="12:00",
    #     task=email_task
    # )
    # print("已添加每天12:00执行的任务")

    # 示例3：添加每周任务（每周一中午12点）
    # service.schedule_weekly(
    #     task_id="weekly_monday",
    #     day_of_week=0,
    #     run_time="12:00",
    #     task=email_task
    # )
    # print("已添加每周一12:00执行的任务")

    # 列出所有任务
    print("\n当前任务列表:")
    jobs = service.list_jobs()
    for job in jobs:
        print(f"  - {job['name']}: 下次执行时间 {job['next_run_time']}")

    # 保持运行以便观察定时执行
    print("\n调度器正在运行，按 Ctrl+C 退出...")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n正在停止调度器...")
        service.stop()
        print("调度器已停止")
