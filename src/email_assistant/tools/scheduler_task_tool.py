from datetime import datetime, timedelta
from ..service.task_manager import TaskManager,get_task_manager
from ..models.scheduler_task_model import ScheduleType
from typing import List, Dict, Any, Optional, Union
from langchain.tools import tool
from ..models.scheduler_task_model import ScheduleType
from datetime import datetime, time
import logging
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

manager = get_task_manager()

def check_existing_task(task_id)-> bool:

    # 检查任务是否已存在（在数据库中）
    existing_task = manager.get_task(task_id)

    if existing_task:
        logger.info(f"定时器任务已存在:{task_id}")
        return True
    else:
        return False

class SchedulerTask_tool():


    @staticmethod
    @tool
    def add_daily_task(
        task_id: str,
        task_name: str,
        recipients: Union[str, List[str]],
        subject: str,
        content: str,
        schedule_type: Union[ScheduleType, str]=ScheduleType.DAILY,
        content_type: str = 'plain',
        sender_name: str = None,
        run_time: Union[time, str] = None,
        description: str = None,
        auto_schedule: bool = True
        ) -> Dict[str,Any]:
        """
        descrption:
            添加每天定时执行任务的工具，当需要在系统内添加周期性的 任务，可以通过此工具，添加定时任务
        params:
            task_id：任务ID,
            task_name： 任务名称
            recipients：收件箱,
            subject：邮件标题
            content：邮件内容
            schedule_type: 定时器类型枚举
                ONCE = "once"  # 一次性任务，指定具体时间
                DAILY = "daily" # 每天定时执行,默认使用此参数
                WEEKLY = "weekly" # 每周定时执行
                INTERVAL = "interval" # 间隔时间执行
                CRON = "cron" # Cron表达式
            content_type: 内容类型，'plain'或'html'
            run_time:每天在哪个时间运行，举例：14:00
            description:任务描述
            auto_schedule: 是否自动添加到调度器，默认为 True
        return: 
            添加定时任务结果， Dict 类型

        """

        #检查任务是否已存在
        if check_existing_task(task_id):
            return {
                'success':False,
                "message":"定时任务已存在，无需添加",
            }
        try:

            add_task_result = manager.add_email_task(
                task_id = task_id,
                task_name = task_name,
                recipients = recipients,
                subject = subject,
                content = content,
                schedule_type =  schedule_type,
                content_type =  content_type,
                sender_name = sender_name,
                run_time = run_time,
                description = description,
                auto_schedule = auto_schedule
            )
            
            if add_task_result['success']:
                return {
                'success': True,
                'message': '一个每天执行的定时任务添加成功',
                'task_id': task_id,
                'task_name': task_name,
                'run_timme':run_time,
                'recipients':recipients
                }
        
        except Exception as e:
            logger.error(f"添加邮件任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'添加任务失败: {str(e)}'
            }

    
    @staticmethod
    @tool
    def add_oneTime_task(
        task_id: str,
        task_name: str,
        recipients: Union[str, List[str]],
        subject: str,
        content: str,
        run_date: Union[datetime, str],
        schedule_type: Union[ScheduleType, str] = ScheduleType.ONCE,
        content_type: str = 'plain',
        sender_name: str = None,
        description: str = None,
        auto_schedule: bool = True
        ) -> Dict[str,Any]:
        """
        descrption:
            添加一次性任务的工具，用于在指定的时间点执行一次邮件发送任务
        params:
            task_id：任务ID,
            task_name： 任务名称
            recipients：收件箱,
            subject：邮件标题
            content：邮件内容
            run_date: 一次性任务执行时间，可以是 datetime 对象或字符串格式（如：'2025-12-27 15:30:00'）
            schedule_type: 定时器类型，一次性任务使用 'once'
            content_type: 内容类型，'plain'或'html'
            sender_name: 发件人名称
            description:任务描述
            auto_schedule: 是否自动添加到调度器，默认为 True
        return:
            添加一次性任务结果， Dict 类型

        """

        #检查任务是否已存在
        if check_existing_task(task_id):
            return {
                'success':False,
                "message":"一次性任务已存在，无需添加",
            }
        try:

            add_task_result = manager.add_email_task(
                task_id = task_id,
                task_name = task_name,
                recipients = recipients,
                subject = subject,
                content = content,
                schedule_type = schedule_type,
                content_type = content_type,
                sender_name = sender_name,
                run_date = run_date,
                description = description,
                auto_schedule = auto_schedule
            )

            if add_task_result['success']:
                return {
                'success': True,
                'message': '一个一次性任务添加成功',
                'task_id': task_id,
                'task_name': task_name,
                'run_date': str(run_date),
                'recipients':recipients
                }

        except Exception as e:
            logger.error(f"添加一次性任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'添加一次性任务失败: {str(e)}'
            }

    @staticmethod
    @tool
    def get_all_task() -> Dict[str,Any]:
        """
        description:
            查询所有已添加到调度器中的的定时任务的工具，通过这个工具，可以查询到定时器中存在哪些任务
        
        return
            返回所有的任务查询结果
        """
        try:
            # 查询所有任务
            tasks = manager.list_tasks()

            # 验证数据是否可序列化
            try:
                json.dumps(tasks)
            except (TypeError, ValueError) as e:
                logger.error(f"任务数据无法序列化: {str(e)}")
                return {
                    'success': False,
                    'message': f'任务数据格式错误，无法序列化: {str(e)}'
                }

            # 统计任务数量
            tasks_number = len(tasks)

            if tasks_number <= 0:
                return {
                    "success":True,
                    "message":"查询调度器，发现目前仅有0个任务",
                    "tasks_number":tasks_number,
                    "task_list":tasks
                }
            else:
                logger.info(f"已查询到{tasks_number}个调度器任务")
                return {
                    "success":True,
                    "messages":[f"已查询到{tasks_number}个调度器任务"],
                    "tasks_number":tasks_number,
                    "task_list":tasks
                }
            
        except Exception as e:
            logger.error(f"查询调度器任务失败: {str(e)}")
            return {
                'success': False,
                'message': f'查询调度器任务失败: {str(e)}'
            }

