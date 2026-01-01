"""
统一数据库管理模块
负责管理所有数据库表的初始化和连接
"""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# 导入所有模型
from .contacts_model import Contact, Base as ContactsBase
from .scheduler_task_model import Base as SchedulerBase  # noqa: F401

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    统一数据库管理器
    管理所有表的创建和数据库连接
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径，默认为 data/data.db
        """
        if db_path is None:
            # 默认数据库路径
            db_path = Path(__file__).parent.parent.parent / "data" / "data.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建数据库引擎
        engine_url = f"sqlite:///{self.db_path.absolute()}"
        self.engine = create_engine(
            engine_url,
            echo=False,
            connect_args={"check_same_thread": False}
        )

        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        logger.info(f"数据库管理器初始化完成，数据库路径: {self.db_path}")

    def init_database(self):
        """
        初始化所有数据库表
        现在所有表都使用 SQLAlchemy ORM
        """
        try:
            # 1. 创建 SQLAlchemy ORM 表（contacts 表）
            ContactsBase.metadata.create_all(bind=self.engine)
            logger.info("✓ Contacts 表初始化完成")

            # 2. 创建 SQLAlchemy ORM 表（scheduler_tasks 表）
            SchedulerBase.metadata.create_all(bind=self.engine)
            logger.info("✓ SchedulerTasks 表初始化完成")

            logger.info("✓ 所有数据库表初始化完成")
            return True

        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
            raise

    def get_session(self) -> Session:
        """
        获取数据库会话

        Returns:
            Session: SQLAlchemy 会话对象
        """
        return self.SessionLocal()

    def get_database_info(self) -> dict:
        """
        获取数据库信息

        Returns:
            dict: 数据库信息
        """
        info = {
            "database_path": str(self.db_path),
            "database_exists": self.db_path.exists(),
            "database_size": None,
            "tables": []
        }

        if self.db_path.exists():
            info["database_size"] = f"{self.db_path.stat().st_size / 1024:.2f} KB"

            # 获取所有表
            try:
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
                tables = cursor.fetchall()
                info["tables"] = [table[0] for table in tables]
                conn.close()
            except Exception as e:
                logger.error(f"获取表列表失败: {str(e)}")

        return info

    def print_database_info(self):
        """打印数据库信息"""
        info = self.get_database_info()

        print("\n" + "=" * 50)
        print("数据库信息")
        print("=" * 50)
        print(f"数据库路径: {info['database_path']}")
        print(f"数据库存在: {info['database_exists']}")
        if info['database_size']:
            print(f"数据库大小: {info['database_size']}")
        print(f"\n数据表 ({len(info['tables'])} 个):")
        for table in info['tables']:
            print(f"  - {table}")
        print("=" * 50 + "\n")


# 创建全局数据库管理器实例
_global_db_manager: Optional[DatabaseManager] = None


def get_database_manager(db_path: Optional[str] = None) -> DatabaseManager:
    """
    获取数据库管理器实例（单例模式）

    Args:
        db_path: 数据库路径 (可选)

    Returns:
        DatabaseManager: 数据库管理器实例
    """
    global _global_db_manager

    if _global_db_manager is None:
        _global_db_manager = DatabaseManager(db_path)

    return _global_db_manager


def init_database(db_path: Optional[str] = None) -> DatabaseManager:
    """
    初始化数据库（便捷函数）

    Args:
        db_path: 数据库路径 (可选)

    Returns:
        DatabaseManager: 数据库管理器实例
    """
    db_manager = get_database_manager(db_path)
    db_manager.init_database()
    return db_manager


if __name__ == "__main__":
    """测试代码"""
    import sys
    from pathlib import Path

    # 添加项目根目录到 Python 路径
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

    print("=== 测试数据库管理器 ===\n")

    # 创建数据库管理器
    db_manager = DatabaseManager()

    # 初始化数据库
    print("初始化数据库...")
    db_manager.init_database()

    # 打印数据库信息
    db_manager.print_database_info()

    print("\n测试完成！")
