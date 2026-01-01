"""
定时器任务数据模型
使用 SQLAlchemy + SQLite 存储和管理定时器任务
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from enum import Enum

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Float,
    Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import IntegrityError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建基类 (使用 SQLAlchemy 2.0 推荐方式)
Base = declarative_base()


class ScheduleType(Enum):
    """定时器类型枚举"""
    ONCE = "once"              # 一次性任务，指定具体时间
    DAILY = "daily"            # 每天定时执行
    WEEKLY = "weekly"          # 每周定时执行
    INTERVAL = "interval"      # 间隔时间执行
    CRON = "cron"              # Cron表达式


class TaskStatus(Enum):
    """任务状态枚举"""
    ACTIVE = "active"          # 激活状态
    PAUSED = "paused"          # 暂停状态
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    DELETED = "deleted"        # 已删除


class SchedulerTask(Base):
    """定时器任务 ORM 模型"""
    __tablename__ = 'scheduler_tasks'

    # 主键和基本信息
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    task_name = Column(String(255), nullable=False)
    schedule_type = Column(String(50), nullable=False, index=True)
    task_status = Column(String(50), nullable=False, default=TaskStatus.ACTIVE.value, index=True)

    # 调度配置
    run_date = Column(String(100), nullable=True)                    # 一次性任务执行时间
    run_time = Column(String(50), nullable=True)                    # 每天/每周任务的执行时间 (HH:MM)
    day_of_week = Column(Integer, nullable=True)                    # 每周任务的星期几 (0-6)
    interval_seconds = Column(Integer, nullable=True)               # 间隔任务的秒数
    cron_expression = Column(String(100), nullable=True)            # Cron表达式

    # 任务数据 (JSON格式)
    task_data = Column(Text, nullable=False)                        # 邮件任务数据或函数配置

    # 元数据
    created_at = Column(String(100), nullable=False)
    updated_at = Column(String(100), nullable=False)
    last_run_at = Column(String(100), nullable=True)
    next_run_at = Column(String(100), nullable=True)
    run_count = Column(Integer, default=0)

    # 备注和标签
    description = Column(Text, nullable=True)
    tags = Column(String(500), nullable=True)                       # 标签，逗号分隔

    # 调度器任务ID (APScheduler的job_id)
    scheduler_job_id = Column(String(255), nullable=True)

    # 定义索引
    __table_args__ = (
        Index('idx_task_id', 'task_id'),
        Index('idx_task_status', 'task_status'),
        Index('idx_schedule_type', 'schedule_type'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'task_name': self.task_name,
            'schedule_type': self.schedule_type,
            'task_status': self.task_status,
            'run_date': self.run_date,
            'run_time': self.run_time,
            'day_of_week': self.day_of_week,
            'interval_seconds': self.interval_seconds,
            'cron_expression': self.cron_expression,
            'task_data': self.task_data,
            'task_data_dict': self._parse_task_data(),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'last_run_at': self.last_run_at,
            'next_run_at': self.next_run_at,
            'run_count': self.run_count,
            'description': self.description,
            'tags': self.tags,
            'scheduler_job_id': self.scheduler_job_id
        }

    def _parse_task_data(self) -> Dict[str, Any]:
        """解析任务数据 JSON"""
        if self.task_data:
            try:
                return json.loads(self.task_data)
            except json.JSONDecodeError:
                return {}
        return {}

    def __repr__(self):
        return f"<SchedulerTask(id={self.id}, task_id='{self.task_id}', name='{self.task_name}', status='{self.task_status}')>"


class TaskExecutionHistory(Base):
    """任务执行历史 ORM 模型"""
    __tablename__ = 'task_execution_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), nullable=False, index=True)
    executed_at = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_duration = Column(Float, nullable=True)  # 执行时长（秒）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'executed_at': self.executed_at,
            'status': self.status,
            'result': self.result,
            'error_message': self.error_message,
            'execution_duration': self.execution_duration
        }

    def __repr__(self):
        return f"<TaskExecutionHistory(id={self.id}, task_id='{self.task_id}', status='{self.status}')>"


class SchedulerTaskModel:
    """
    定时器任务数据模型
    提供基于 SQLAlchemy 的 CRUD 操作接口
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化任务模型

        Args:
            db_path: 数据库文件路径，默认为 data/data.db
        """
        if db_path is None:
            # 默认数据库路径 - 统一使用 data.db
            db_path = Path(__file__).parent.parent.parent / "data" / "data.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建数据库引擎
        engine_url = f"sqlite:///{self.db_path.absolute()}"
        self.engine = create_engine(
            engine_url,
            echo=False,  # 设置为 True 可以看到 SQL 语句
            connect_args={"check_same_thread": False}  # SQLite 特有配置
        )

        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        # 创建表
        self._init_database()

        logger.info(f"任务模型初始化完成，数据库路径: {self.db_path}")

    def _init_database(self) -> None:
        """初始化数据库表"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("数据库表初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
            raise

    def _get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()

    # ==================== 任务 CRUD 操作 ====================

    def add_task(self, task_data: Dict[str, Any]) -> bool:
        """
        添加任务到数据库

        Args:
            task_data: 任务数据字典，包含以下字段：
                - task_id: 任务ID (必需)
                - task_name: 任务名称 (必需)
                - schedule_type: 调度类型 (必需)
                - task_data_dict: 任务数据 (必需)
                - run_date: 一次性任务执行时间 (可选)
                - run_time: 每天/每周任务执行时间 (可选)
                - day_of_week: 每周任务的星期几 (可选)
                - interval_seconds: 间隔任务秒数 (可选)
                - cron_expression: Cron表达式 (可选)
                - description: 描述 (可选)
                - tags: 标签 (可选)

        Returns:
            bool: 是否添加成功
        """
        session = self._get_session()
        try:
            # 检查必需字段
            required_fields = ['task_id', 'task_name', 'schedule_type', 'task_data_dict']
            for field in required_fields:
                if field not in task_data:
                    raise ValueError(f"缺少必需字段: {field}")

            # 检查任务ID是否已存在
            existing = session.query(SchedulerTask).filter(
                SchedulerTask.task_id == task_data['task_id']
            ).first()
            if existing:
                logger.warning(f"任务ID已存在: {task_data['task_id']}")
                return False

            now = datetime.now().isoformat()

            # 创建任务对象
            task = SchedulerTask(
                task_id=task_data['task_id'],
                task_name=task_data['task_name'],
                schedule_type=task_data['schedule_type'],
                task_status=TaskStatus.ACTIVE.value,
                run_date=task_data.get('run_date'),
                run_time=task_data.get('run_time'),
                day_of_week=task_data.get('day_of_week'),
                interval_seconds=task_data.get('interval_seconds'),
                cron_expression=task_data.get('cron_expression'),
                task_data=json.dumps(task_data['task_data_dict'], ensure_ascii=False),
                created_at=now,
                updated_at=now,
                description=task_data.get('description', ''),
                tags=task_data.get('tags', '')
            )

            session.add(task)
            session.commit()

            logger.info(f"任务已添加到数据库: {task_data['task_id']}")
            return True

        except IntegrityError as e:
            session.rollback()
            logger.warning(f"任务ID已存在: {task_data.get('task_id', 'unknown')}")
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"添加任务失败: {str(e)}")
            return False
        finally:
            session.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        根据任务ID获取任务

        Args:
            task_id: 任务ID

        Returns:
            Dict: 任务数据，如果不存在返回 None
        """
        session = self._get_session()
        try:
            task = session.query(SchedulerTask).filter(
                SchedulerTask.task_id == task_id,
                SchedulerTask.task_status != TaskStatus.DELETED.value
            ).first()

            if task:
                return task.to_dict()
            return None

        except Exception as e:
            logger.error(f"获取任务失败: {str(e)}")
            return None
        finally:
            session.close()

    def get_all_tasks(
        self,
        status: Optional[TaskStatus] = None,
        schedule_type: Optional[ScheduleType] = None
    ) -> List[Dict[str, Any]]:
        """
        获取所有任务

        Args:
            status: 任务状态过滤 (可选)
            schedule_type: 调度类型过滤 (可选)

        Returns:
            List[Dict]: 任务列表
        """
        session = self._get_session()
        try:
            query = session.query(SchedulerTask).filter(
                SchedulerTask.task_status != TaskStatus.DELETED.value
            )

            if status:
                query = query.filter(SchedulerTask.task_status == status.value)

            if schedule_type:
                query = query.filter(SchedulerTask.schedule_type == schedule_type.value)

            # 按创建时间倒序排列
            query = query.order_by(SchedulerTask.created_at.desc())

            tasks = query.all()

            return [task.to_dict() for task in tasks]

        except Exception as e:
            logger.error(f"获取任务列表失败: {str(e)}")
            return []
        finally:
            session.close()

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新任务信息

        Args:
            task_id: 任务ID
            updates: 要更新的字段字典

        Returns:
            bool: 是否更新成功
        """
        session = self._get_session()
        try:
            # 允许更新的字段
            allowed_fields = {
                'task_name', 'schedule_type', 'task_status', 'run_date',
                'run_time', 'day_of_week', 'interval_seconds', 'cron_expression',
                'description', 'tags', 'next_run_at', 'scheduler_job_id'
            }

            # 过滤允许更新的字段
            update_fields = {k: v for k, v in updates.items() if k in allowed_fields}

            if not update_fields:
                logger.warning("没有需要更新的字段")
                return False

            # 查找任务
            task = session.query(SchedulerTask).filter(
                SchedulerTask.task_id == task_id
            ).first()

            if not task:
                logger.warning(f"任务不存在: {task_id}")
                return False

            # 更新字段
            for field, value in update_fields.items():
                setattr(task, field, value)

            # 更新 updated_at
            task.updated_at = datetime.now().isoformat()

            session.commit()
            logger.info(f"任务已更新: {task_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"更新任务失败: {str(e)}")
            return False
        finally:
            session.close()

    def delete_task(self, task_id: str, soft_delete: bool = True) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID
            soft_delete: 是否软删除（标记为deleted），默认True

        Returns:
            bool: 是否删除成功
        """
        session = self._get_session()
        try:
            task = session.query(SchedulerTask).filter(
                SchedulerTask.task_id == task_id
            ).first()

            if not task:
                logger.warning(f"任务不存在: {task_id}")
                return False

            if soft_delete:
                # 软删除：标记为deleted
                task.task_status = TaskStatus.DELETED.value
                task.updated_at = datetime.now().isoformat()
            else:
                # 硬删除：从数据库中移除
                session.delete(task)

            session.commit()

            logger.info(f"任务已删除: {task_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"删除任务失败: {str(e)}")
            return False
        finally:
            session.close()

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态

        Returns:
            bool: 是否更新成功
        """
        return self.update_task(task_id, {'task_status': status.value})

    def increment_run_count(self, task_id: str) -> bool:
        """
        增加任务执行次数

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否更新成功
        """
        session = self._get_session()
        try:
            task = session.query(SchedulerTask).filter(
                SchedulerTask.task_id == task_id
            ).first()

            if not task:
                logger.warning(f"任务不存在: {task_id}")
                return False

            now = datetime.now().isoformat()
            task.run_count += 1
            task.last_run_at = now
            task.updated_at = now

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"更新执行次数失败: {str(e)}")
            return False
        finally:
            session.close()

    # ==================== 执行历史操作 ====================

    def add_execution_history(
        self,
        task_id: str,
        status: str,
        result: Optional[str] = None,
        error_message: Optional[str] = None,
        execution_duration: Optional[float] = None
    ) -> bool:
        """
        添加任务执行历史记录

        Args:
            task_id: 任务ID
            status: 执行状态
            result: 执行结果 (可选)
            error_message: 错误信息 (可选)
            execution_duration: 执行时长（秒）(可选)

        Returns:
            bool: 是否添加成功
        """
        session = self._get_session()
        try:
            history = TaskExecutionHistory(
                task_id=task_id,
                executed_at=datetime.now().isoformat(),
                status=status,
                result=result,
                error_message=error_message,
                execution_duration=execution_duration
            )

            session.add(history)
            session.commit()

            return True

        except Exception as e:
            session.rollback()
            logger.error(f"添加执行历史失败: {str(e)}")
            return False
        finally:
            session.close()

    def get_execution_history(
        self,
        task_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取任务执行历史

        Args:
            task_id: 任务ID
            limit: 返回记录数量限制

        Returns:
            List[Dict]: 执行历史列表
        """
        session = self._get_session()
        try:
            histories = session.query(TaskExecutionHistory).filter(
                TaskExecutionHistory.task_id == task_id
            ).order_by(
                TaskExecutionHistory.executed_at.desc()
            ).limit(limit).all()

            return [history.to_dict() for history in histories]

        except Exception as e:
            logger.error(f"获取执行历史失败: {str(e)}")
            return []
        finally:
            session.close()

    # ==================== 辅助方法 ====================

    def task_exists(self, task_id: str) -> bool:
        """
        检查任务是否存在

        Args:
            task_id: 任务ID

        Returns:
            bool: 任务是否存在
        """
        session = self._get_session()
        try:
            count = session.query(SchedulerTask).filter(
                SchedulerTask.task_id == task_id,
                SchedulerTask.task_status != TaskStatus.DELETED.value
            ).count()

            return count > 0

        except Exception as e:
            logger.error(f"检查任务是否存在失败: {str(e)}")
            return False
        finally:
            session.close()

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """
        获取所有激活状态的任务

        Returns:
            List[Dict]: 激活任务列表
        """
        return self.get_all_tasks(status=TaskStatus.ACTIVE)

    def cleanup_old_history(self, days: int = 30) -> int:
        """
        清理旧的执行历史记录

        Args:
            days: 保留天数

        Returns:
            int: 清理的记录数
        """
        session = self._get_session()
        try:
            from datetime import timedelta

            cutoff_date = datetime.now() - timedelta(days=days)

            # 查询需要删除的记录
            histories = session.query(TaskExecutionHistory).filter(
                TaskExecutionHistory.executed_at < cutoff_date.isoformat()
            ).all()

            deleted_count = len(histories)

            # 删除记录
            for history in histories:
                session.delete(history)

            session.commit()

            logger.info(f"清理了 {deleted_count} 条执行历史记录")
            return deleted_count

        except Exception as e:
            session.rollback()
            logger.error(f"清理执行历史失败: {str(e)}")
            return 0
        finally:
            session.close()


# 创建全局实例（延迟初始化）
_global_model: Optional[SchedulerTaskModel] = None


def get_task_model(db_path: Optional[str] = None) -> SchedulerTaskModel:
    """
    获取任务模型实例（单例模式）

    Args:
        db_path: 数据库路径 (可选)

    Returns:
        SchedulerTaskModel: 任务模型实例
    """
    global _global_model

    if _global_model is None:
        _global_model = SchedulerTaskModel(db_path)

    return _global_model


if __name__ == "__main__":
    """测试代码"""
    print("=== 测试任务模型 ===\n")

    # 创建模型实例
    model = SchedulerTaskModel()

    # 测试添加任务
    test_task = {
        'task_id': 'test_once_task',
        'task_name': '测试一次性任务',
        'schedule_type': ScheduleType.ONCE.value,
        'task_data_dict': {
            'type': 'email',
            'recipients': 'test@example.com',
            'subject': '测试邮件',
            'content': '这是一封测试邮件'
        },
        'run_date': datetime(2025, 12, 31, 12, 0).isoformat(),
        'description': '用于测试的一次性任务',
        'tags': 'test,email'
    }

    print("添加测试任务...")
    if model.add_task(test_task):
        print("✓ 任务添加成功")
    else:
        print("✗ 任务添加失败")

    # 查询任务
    print("\n查询任务...")
    task = model.get_task('test_once_task')
    if task:
        print(f"✓ 找到任务: {task['task_name']}")
        print(f"  调度类型: {task['schedule_type']}")
        print(f"  状态: {task['task_status']}")
    else:
        print("✗ 未找到任务")

    # 获取所有任务
    print("\n获取所有任务...")
    all_tasks = model.get_all_tasks()
    print(f"✓ 共有 {len(all_tasks)} 个任务")

    # 清理测试数据
    print("\n清理测试数据...")
    model.delete_task('test_once_task', soft_delete=False)
    print("✓ 测试数据已清理")

    print("\n测试完成！")
