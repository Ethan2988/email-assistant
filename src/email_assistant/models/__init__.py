"""
数据模型模块
包含所有数据模型和数据库管理的导出
"""

from .contacts_model import (
    Contact,
    ContactsModel,
    get_contacts_model
)

from .scheduler_task_model import (
    ScheduleType,
    TaskStatus,
    SchedulerTaskModel,
    get_task_model
)

from .database import (
    DatabaseManager,
    get_database_manager,
    init_database
)

__all__ = [
    # Contacts 模型
    "Contact",
    "ContactsModel",
    "get_contacts_model",

    # SchedulerTask 模型
    "ScheduleType",
    "TaskStatus",
    "SchedulerTaskModel",
    "get_task_model",

    # 数据库管理
    "DatabaseManager",
    "get_database_manager",
    "init_database",
]
