"""
定时器任务管理器
负责任务的增删改查，并与调度器服务集成
"""

import logging
from datetime import datetime, time
from typing import Dict, Any, List, Optional, Callable, Union

from ..models.scheduler_task_model import (
    SchedulerTaskModel,
    ScheduleType,
    TaskStatus
)
from .scheduler_service import SchedulerService, EmailTask

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TaskManager:
    """
    任务管理器

    职责：
    1. 管理任务的持久化存储
    2. 与调度器服务集成
    3. 提供任务的增删改查接口
    4. 启动时自动加载数据库中的任务到调度器
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        task_model: Optional[SchedulerTaskModel] = None,
        scheduler_service: Optional[SchedulerService] = None
    ):
        """
        初始化任务管理器

        Args:
            task_model: 任务模型实例（可选）
            scheduler_service: 调度器服务实例（可选）
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.task_model = task_model or SchedulerTaskModel()
        self.scheduler_service = scheduler_service or SchedulerService()
        self._initialized = True

        logger.info("任务管理器初始化完成")

    # ==================== 任务添加操作 ====================

    def add_email_task(
        self,
        task_id: str,
        task_name: str,
        recipients: Union[str, List[str]],
        subject: str,
        content: str,
        schedule_type: Union[ScheduleType, str],
        content_type: str = 'plain',
        cc_emails: Union[str, List[str]] = None,
        bcc_emails: Union[str, List[str]] = None,
        attachment_paths: List[str] = None,
        sender_name: str = None,
        # 调度参数
        run_date: Union[datetime, str] = None,
        run_time: Union[time, str] = None,
        day_of_week: int = None,
        interval_seconds: int = None,
        cron_expression: str = None,
        # 元数据
        description: str = None,
        tags: str = None,
        auto_schedule: bool = True
    ) -> Dict[str, Any]:
        """
        添加邮件任务

        Args:
            task_id: 任务ID
            task_name: 任务名称
            recipients: 收件人邮箱
            subject: 邮件主题
            content: 邮件内容
            schedule_type: 调度类型
            content_type: 内容类型 (plain/html)
            cc_emails: 抄送邮箱
            bcc_emails: 密送邮箱
            attachment_paths: 附件路径列表
            sender_name: 发件人名称
            run_date: 一次性任务执行时间
            run_time: 每天/每周任务执行时间
            day_of_week: 每周任务的星期几 (0-6)
            interval_seconds: 间隔任务秒数
            cron_expression: Cron表达式
            description: 任务描述
            tags: 标签
            auto_schedule: 是否自动添加到调度器

        Returns:
            Dict: 操作结果
        """
        try:
            # 检查任务是否已存在
            if self.task_model.task_exists(task_id):
                return {
                    'success': False,
                    'message': f'任务ID已存在: {task_id}'
                }

            # 统一 schedule_type 为字符串
            if isinstance(schedule_type, ScheduleType):
                schedule_type = schedule_type.value

            # 构建任务数据
            task_data_dict = {
                'type': 'email',
                'recipients': recipients,
                'subject': subject,
                'content': content,
                'content_type': content_type,
                'cc_emails': cc_emails,
                'bcc_emails': bcc_emails,
                'attachment_paths': attachment_paths,
                'sender_name': sender_name
            }

            # 准备数据库记录
            db_task_data = {
                'task_id': task_id,
                'task_name': task_name,
                'schedule_type': schedule_type,
                'task_data_dict': task_data_dict,
                'run_date': run_date.isoformat() if isinstance(run_date, datetime) else run_date,
                'run_time': run_time.strftime('%H:%M') if isinstance(run_time, time) else run_time,
                'day_of_week': day_of_week,
                'interval_seconds': interval_seconds,
                'cron_expression': cron_expression,
                'description': description,
                'tags': tags
            }

            # 添加到数据库
            if not self.task_model.add_task(db_task_data):
                return {
                    'success': False,
                    'message': '添加任务到数据库失败'
                }

            # 如果需要，添加到调度器
            if auto_schedule:
                schedule_result = self._schedule_task_from_db(task_id, schedule_type)
                if not schedule_result['success']:
                    # 如果调度失败，从数据库移除
                    self.task_model.delete_task(task_id, soft_delete=False)
                    return schedule_result

            logger.info(f"邮件任务已添加: {task_id}")
            return {
                'success': True,
                'message': '任务添加成功',
                'task_id': task_id
            }

        except Exception as e:
            logger.error(f"添加邮件任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'添加任务失败: {str(e)}'
            }

    def add_custom_task(
        self,
        task_id: str,
        task_name: str,
        task_func: Callable,
        schedule_type: Union[ScheduleType, str],
        # 调度参数
        run_date: Union[datetime, str] = None,
        run_time: Union[time, str] = None,
        day_of_week: int = None,
        interval_seconds: int = None,
        cron_expression: str = None,
        # 元数据
        description: str = None,
        tags: str = None,
        auto_schedule: bool = True
    ) -> Dict[str, Any]:
        """
        添加自定义任务

        Args:
            task_id: 任务ID
            task_name: 任务名称
            task_func: 任务函数
            schedule_type: 调度类型
            run_date: 一次性任务执行时间
            run_time: 每天/每周任务执行时间
            day_of_week: 每周任务的星期几
            interval_seconds: 间隔任务秒数
            cron_expression: Cron表达式
            description: 任务描述
            tags: 标签
            auto_schedule: 是否自动添加到调度器

        Returns:
            Dict: 操作结果
        """
        try:
            # 检查任务是否已存在
            if self.task_model.task_exists(task_id):
                return {
                    'success': False,
                    'message': f'任务ID已存在: {task_id}'
                }

            # 统一 schedule_type 为字符串
            if isinstance(schedule_type, ScheduleType):
                schedule_type = schedule_type.value

            # 构建任务数据（存储函数引用的字符串表示）
            task_data_dict = {
                'type': 'custom',
                'func_name': task_func.__name__,
                'func_module': task_func.__module__
            }

            # 保存函数引用到内存（无法序列化到数据库）
            if not hasattr(self, '_custom_functions'):
                self._custom_functions = {}
            self._custom_functions[task_id] = task_func

            # 准备数据库记录
            db_task_data = {
                'task_id': task_id,
                'task_name': task_name,
                'schedule_type': schedule_type,
                'task_data_dict': task_data_dict,
                'run_date': run_date.isoformat() if isinstance(run_date, datetime) else run_date,
                'run_time': run_time.strftime('%H:%M') if isinstance(run_time, time) else run_time,
                'day_of_week': day_of_week,
                'interval_seconds': interval_seconds,
                'cron_expression': cron_expression,
                'description': description,
                'tags': tags
            }

            # 添加到数据库
            if not self.task_model.add_task(db_task_data):
                return {
                    'success': False,
                    'message': '添加任务到数据库失败'
                }

            # 如果需要，添加到调度器
            if auto_schedule:
                schedule_result = self._schedule_task_from_db(task_id, schedule_type)
                if not schedule_result['success']:
                    # 如果调度失败，从数据库移除
                    self.task_model.delete_task(task_id, soft_delete=False)
                    return schedule_result

            logger.info(f"自定义任务已添加: {task_id}")
            return {
                'success': True,
                'message': '任务添加成功',
                'task_id': task_id
            }

        except Exception as e:
            logger.error(f"添加自定义任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'添加任务失败: {str(e)}'
            }

    # ==================== 任务查询操作 ====================

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息

        Args:
            task_id: 任务ID

        Returns:
            Dict: 任务信息，不存在返回 None
        """
        return self.task_model.get_task(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        schedule_type: Optional[ScheduleType] = None
    ) -> List[Dict[str, Any]]:
        """
        列出所有任务

        Args:
            status: 任务状态过滤
            schedule_type: 调度类型过滤

        Returns:
            List[Dict]: 任务列表
        """
        return self.task_model.get_all_tasks(status, schedule_type)

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """获取所有激活状态的任务"""
        return self.task_model.get_active_tasks()

    # ==================== 任务更新操作 ====================

    def update_task(
        self,
        task_id: str,
        updates: Dict[str, Any],
        reschedule: bool = False
    ) -> Dict[str, Any]:
        """
        更新任务信息

        Args:
            task_id: 任务ID
            updates: 要更新的字段
            reschedule: 是否重新调度任务

        Returns:
            Dict: 操作结果
        """
        try:
            # 检查任务是否存在
            if not self.task_model.task_exists(task_id):
                return {
                    'success': False,
                    'message': f'任务不存在: {task_id}'
                }

            # 如果需要重新调度，先从调度器移除
            if reschedule:
                self.scheduler_service.remove_job(task_id)

            # 更新数据库
            success = self.task_model.update_task(task_id, updates)

            if not success:
                return {
                    'success': False,
                    'message': '更新任务失败'
                }

            # 如果需要重新调度
            if reschedule:
                task = self.task_model.get_task(task_id)
                if task:
                    schedule_result = self._schedule_task_from_db(
                        task_id,
                        task['schedule_type']
                    )
                    if not schedule_result['success']:
                        return schedule_result

            logger.info(f"任务已更新: {task_id}")
            return {
                'success': True,
                'message': '任务更新成功'
            }

        except Exception as e:
            logger.error(f"更新任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'更新任务失败: {str(e)}'
            }

    def pause_task(self, task_id: str) -> Dict[str, Any]:
        """
        暂停任务

        Args:
            task_id: 任务ID

        Returns:
            Dict: 操作结果
        """
        try:
            # 暂停调度器中的任务
            if not self.scheduler_service.pause_job(task_id):
                return {
                    'success': False,
                    'message': '暂停调度器任务失败'
                }

            # 更新数据库状态
            self.task_model.update_task_status(task_id, TaskStatus.PAUSED)

            logger.info(f"任务已暂停: {task_id}")
            return {
                'success': True,
                'message': '任务已暂停'
            }

        except Exception as e:
            logger.error(f"暂停任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'暂停任务失败: {str(e)}'
            }

    def resume_task(self, task_id: str) -> Dict[str, Any]:
        """
        恢复任务

        Args:
            task_id: 任务ID

        Returns:
            Dict: 操作结果
        """
        try:
            # 恢复调度器中的任务
            if not self.scheduler_service.resume_job(task_id):
                return {
                    'success': False,
                    'message': '恢复调度器任务失败'
                }

            # 更新数据库状态
            self.task_model.update_task_status(task_id, TaskStatus.ACTIVE)

            logger.info(f"任务已恢复: {task_id}")
            return {
                'success': True,
                'message': '任务已恢复'
            }

        except Exception as e:
            logger.error(f"恢复任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'恢复任务失败: {str(e)}'
            }

    # ==================== 任务删除操作 ====================

    def remove_task(
        self,
        task_id: str,
        soft_delete: bool = True
    ) -> Dict[str, Any]:
        """
        删除任务

        Args:
            task_id: 任务ID
            soft_delete: 是否软删除

        Returns:
            Dict: 操作结果
        """
        try:
            # 从调度器移除
            self.scheduler_service.remove_job(task_id)

            # 从数据库删除
            success = self.task_model.delete_task(task_id, soft_delete)

            if not success:
                return {
                    'success': False,
                    'message': f'任务不存在: {task_id}'
                }

            # 如果是自定义任务，从内存中移除
            if hasattr(self, '_custom_functions') and task_id in self._custom_functions:
                del self._custom_functions[task_id]

            logger.info(f"任务已删除: {task_id}")
            return {
                'success': True,
                'message': '任务已删除'
            }

        except Exception as e:
            logger.error(f"删除任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'删除任务失败: {str(e)}'
            }

    # ==================== 任务加载操作 ====================

    def load_tasks_from_db(self) -> Dict[str, Any]:
        """
        从数据库加载所有激活的任务到调度器

        Returns:
            Dict: 加载结果
        """
        try:
            # 获取所有激活的任务
            active_tasks = self.task_model.get_active_tasks()

            loaded_count = 0
            failed_tasks = []

            for task in active_tasks:
                try:
                    result = self._schedule_task_from_db(
                        task['task_id'],
                        task['schedule_type']
                    )

                    if result['success']:
                        loaded_count += 1
                    else:
                        failed_tasks.append({
                            'task_id': task['task_id'],
                            'error': result.get('message', '未知错误')
                        })

                except Exception as e:
                    logger.error(f"加载任务失败 {task['task_id']}: {str(e)}")
                    failed_tasks.append({
                        'task_id': task['task_id'],
                        'error': str(e)
                    })

            logger.info(f"从数据库加载了 {loaded_count} 个任务")

            return {
                'success': True,
                'loaded_count': loaded_count,
                'total_count': len(active_tasks),
                'failed_tasks': failed_tasks,
                'message': f'成功加载 {loaded_count}/{len(active_tasks)} 个任务'
            }

        except Exception as e:
            logger.error(f"从数据库加载任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'加载任务失败: {str(e)}'
            }

    # ==================== 内部辅助方法 ====================

    def _schedule_task_from_db(
        self,
        task_id: str,
        schedule_type: str
    ) -> Dict[str, Any]:
        """
        从数据库任务数据创建调度器任务

        Args:
            task_id: 任务ID
            schedule_type: 调度类型

        Returns:
            Dict: 调度结果
        """
        try:
            # 检查任务是否已在调度器中
            if self.scheduler_service.scheduler and self.scheduler_service.scheduler.get_job(task_id):
                logger.debug(f"任务 {task_id} 已在调度器中，跳过调度")
                return {
                    'success': True,
                    'message': '任务已在调度器中'
                }

            # 从数据库获取任务信息
            task = self.task_model.get_task(task_id)
            if not task:
                return {
                    'success': False,
                    'message': f'任务不存在: {task_id}'
                }

            task_data_dict = task['task_data_dict']

            # 根据任务类型构建任务对象
            if task_data_dict.get('type') == 'email':
                # 创建邮件任务
                email_task = EmailTask(
                    task_id=task_id,
                    recipients=task_data_dict['recipients'],
                    subject=task_data_dict['subject'],
                    content=task_data_dict['content'],
                    content_type=task_data_dict.get('content_type', 'plain'),
                    cc_emails=task_data_dict.get('cc_emails'),
                    bcc_emails=task_data_dict.get('bcc_emails'),
                    attachment_paths=task_data_dict.get('attachment_paths'),
                    sender_name=task_data_dict.get('sender_name')
                )

                task_obj = email_task

            elif task_data_dict.get('type') == 'custom':
                # 获取自定义函数
                if not hasattr(self, '_custom_functions') or task_id not in self._custom_functions:
                    return {
                        'success': False,
                        'message': f'自定义函数未找到: {task_id}'
                    }
                task_obj = self._custom_functions[task_id]

            else:
                return {
                    'success': False,
                    'message': f'未知任务类型: {task_data_dict.get("type")}'
                }

            # 根据调度类型添加到调度器
            success = False

            if schedule_type == ScheduleType.ONCE.value:
                success = self.scheduler_service.schedule_once(
                    task_id=task_id,
                    run_date=task['run_date'],
                    task=task_obj
                )

            elif schedule_type == ScheduleType.DAILY.value:
                success = self.scheduler_service.schedule_daily(
                    task_id=task_id,
                    run_time=task['run_time'],
                    task=task_obj
                )

            elif schedule_type == ScheduleType.WEEKLY.value:
                success = self.scheduler_service.schedule_weekly(
                    task_id=task_id,
                    day_of_week=task['day_of_week'],
                    run_time=task['run_time'],
                    task=task_obj
                )

            elif schedule_type == ScheduleType.INTERVAL.value:
                success = self.scheduler_service.schedule_interval(
                    task_id=task_id,
                    interval_seconds=task['interval_seconds'],
                    task=task_obj
                )

            elif schedule_type == ScheduleType.CRON.value:
                success = self.scheduler_service.schedule_cron(
                    task_id=task_id,
                    cron_expression=task['cron_expression'],
                    task=task_obj
                )

            else:
                return {
                    'success': False,
                    'message': f'未知调度类型: {schedule_type}'
                }

            if success:
                # 更新数据库中的 scheduler_job_id
                self.task_model.update_task(
                    task_id,
                    {'scheduler_job_id': task_id}
                )

                return {
                    'success': True,
                    'message': '任务调度成功'
                }
            else:
                return {
                    'success': False,
                    'message': '调度器添加任务失败'
                }

        except Exception as e:
            logger.error(f"调度任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'调度任务失败: {str(e)}'
            }


# 创建全局实例
_global_task_manager: Optional[TaskManager] = None


def get_task_manager(
    task_model: Optional[SchedulerTaskModel] = None,
    scheduler_service: Optional[SchedulerService] = None
) -> TaskManager:
    """
    获取任务管理器实例（单例模式）

    Args:
        task_model: 任务模型实例（可选）
        scheduler_service: 调度器服务实例（可选）

    Returns:
        TaskManager: 任务管理器实例
    """
    global _global_task_manager

    if _global_task_manager is None:
        _global_task_manager = TaskManager(task_model, scheduler_service)

    return _global_task_manager


if __name__ == "__main__":
    """测试代码"""
    print("=== 测试任务管理器 ===\n")

    # 创建任务管理器
    manager = TaskManager()

    # 测试添加邮件任务
    from datetime import datetime, timedelta

    test_time = datetime.now() + timedelta(minutes=1)

    result = manager.add_email_task(
        task_id='test_manager_task',
        task_name='测试任务管理器',
        recipients='test@example.com',
        subject='测试邮件',
        content='这是通过任务管理器发送的测试邮件',
        schedule_type=ScheduleType.ONCE,
        run_date=test_time,
        description='用于测试任务管理器',
        auto_schedule=False  # 测试时不自动调度
    )

    print(f"添加任务结果: {result}")

    # 查询任务
    task = manager.get_task('test_manager_task')
    if task:
        print(f"\n任务信息:")
        print(f"  名称: {task['task_name']}")
        print(f"  类型: {task['schedule_type']}")
        print(f"  状态: {task['task_status']}")

    # 列出所有任务
    all_tasks = manager.list_tasks()
    print(f"\n共有 {len(all_tasks)} 个任务")

    # 清理测试数据
    manager.remove_task('test_manager_task', soft_delete=False)
    print("\n测试数据已清理")

    print("\n测试完成！")
