"""
联系人数据模型
使用 SQLAlchemy + SQLite 实现联系人管理
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, DateTime, or_
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


class Contact(Base):
    """联系人 ORM 模型"""
    __tablename__ = 'contacts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'remark': self.remark,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<Contact(id={self.id}, name='{self.name}', email='{self.email}')>"


class ContactsModel:
    """
    联系人数据模型
    提供基于 SQLAlchemy 的 CRUD 操作接口
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化联系人模型

        Args:
            db_path: 数据库文件路径，默认为 data/contacts.db
        """
        if db_path is None:
            # 默认数据库路径 - 统一使用 data.db
            db_path = Path(__file__).parent.parent.parent / "data" / "data.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建数据库引擎
        # sqlite:///<absolute_path>
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

        logger.info(f"联系人模型初始化完成，数据库路径: {self.db_path}")

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

    # ==================== 联系人 CRUD 操作 ====================

    def add_contact(self, name: str, email: str, remark: Optional[str] = None) -> Optional[Contact]:
        """
        添加联系人

        Args:
            name: 联系人姓名
            email: 联系人邮箱
            remark: 备注

        Returns:
            Contact: 创建的联系人对象，失败返回 None
        """
        session = self._get_session()
        try:
            # 检查邮箱是否已存在
            existing = session.query(Contact).filter(Contact.email == email).first()
            if existing:
                logger.warning(f"邮箱已存在: {email}")
                return None

            contact = Contact(
                name=name,
                email=email,
                remark=remark
            )

            session.add(contact)
            session.commit()
            session.refresh(contact)

            logger.info(f"联系人已添加: {name} ({email})")
            return contact

        except Exception as e:
            session.rollback()
            logger.error(f"添加联系人失败: {str(e)}")
            return None
        finally:
            session.close()

    def get_contact_by_id(self, contact_id: int) -> Optional[Contact]:
        """
        根据 ID 获取联系人

        Args:
            contact_id: 联系人 ID

        Returns:
            Contact: 联系人对象，不存在返回 None
        """
        session = self._get_session()
        try:
            contact = session.query(Contact).filter(Contact.id == contact_id).first()
            return contact
        except Exception as e:
            logger.error(f"获取联系人失败: {str(e)}")
            return None
        finally:
            session.close()

    def get_contact_by_email(self, email: str) -> Optional[Contact]:
        """
        根据邮箱获取联系人

        Args:
            email: 联系人邮箱

        Returns:
            Contact: 联系人对象，不存在返回 None
        """
        session = self._get_session()
        try:
            contact = session.query(Contact).filter(Contact.email == email).first()
            return contact
        except Exception as e:
            logger.error(f"获取联系人失败: {str(e)}")
            return None
        finally:
            session.close()

    def search_contacts(
        self,
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        email: Optional[str] = None,
        limit: int = 100
    ) -> List[Contact]:
        """
        搜索联系人（支持模糊查询）

        Args:
            keyword: 关键字（在 id、name、email 中搜索）
            name: 姓名关键字（模糊匹配）
            email: 邮箱关键字（模糊匹配）
            limit: 返回结果数量限制

        Returns:
            List[Contact]: 联系人列表
        """
        session = self._get_session()
        try:
            query = session.query(Contact)

            # 优先使用 keyword 全局搜索
            if keyword:
                # 尝试将 keyword 转换为 ID
                try:
                    keyword_id = int(keyword)
                    query = query.filter(
                        or_(
                            Contact.id == keyword_id,
                            Contact.name.like(f'%{keyword}%'),
                            Contact.email.like(f'%{keyword}%')
                        )
                    )
                except ValueError:
                    # keyword 不是数字，只在 name 和 email 中搜索
                    query = query.filter(
                        or_(
                            Contact.name.like(f'%{keyword}%'),
                            Contact.email.like(f'%{keyword}%')
                        )
                    )
            else:
                # 分别搜索 name 和 email
                if name:
                    query = query.filter(Contact.name.like(f'%{name}%'))
                if email:
                    query = query.filter(Contact.email.like(f'%{email}%'))

            # 按创建时间倒序排列
            query = query.order_by(Contact.created_at.desc())

            # 限制结果数量
            contacts = query.limit(limit).all()

            return contacts

        except Exception as e:
            logger.error(f"搜索联系人失败: {str(e)}")
            return []
        finally:
            session.close()

    def get_all_contacts(self, limit: int = 1000) -> List[Contact]:
        """
        获取所有联系人

        Args:
            limit: 返回结果数量限制

        Returns:
            List[Contact]: 联系人列表
        """
        session = self._get_session()
        try:
            contacts = session.query(Contact)\
                .order_by(Contact.created_at.desc())\
                .limit(limit)\
                .all()
            return contacts
        except Exception as e:
            logger.error(f"获取联系人列表失败: {str(e)}")
            return []
        finally:
            session.close()

    def update_contact(
        self,
        contact_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        remark: Optional[str] = None
    ) -> bool:
        """
        更新联系人信息

        Args:
            contact_id: 联系人 ID
            name: 新姓名（可选）
            email: 新邮箱（可选）
            remark: 新备注（可选）

        Returns:
            bool: 是否更新成功
        """
        session = self._get_session()
        try:
            contact = session.query(Contact).filter(Contact.id == contact_id).first()

            if not contact:
                logger.warning(f"联系人不存在: ID={contact_id}")
                return False

            # 更新字段
            if name is not None:
                contact.name = name
            if email is not None:
                # 检查邮箱是否已被其他联系人使用
                existing = session.query(Contact).filter(
                    Contact.email == email,
                    Contact.id != contact_id
                ).first()
                if existing:
                    logger.warning(f"邮箱已被使用: {email}")
                    return False
                contact.email = email
            if remark is not None:
                contact.remark = remark

            # 更新时间戳会自动更新
            session.commit()

            logger.info(f"联系人已更新: ID={contact_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"更新联系人失败: {str(e)}")
            return False
        finally:
            session.close()

    def delete_contact(self, contact_id: int) -> bool:
        """
        删除联系人

        Args:
            contact_id: 联系人 ID

        Returns:
            bool: 是否删除成功
        """
        session = self._get_session()
        try:
            contact = session.query(Contact).filter(Contact.id == contact_id).first()

            if not contact:
                logger.warning(f"联系人不存在: ID={contact_id}")
                return False

            session.delete(contact)
            session.commit()

            logger.info(f"联系人已删除: ID={contact_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"删除联系人失败: {str(e)}")
            return False
        finally:
            session.close()

    def contact_exists(self, email: str) -> bool:
        """
        检查联系人是否存在

        Args:
            email: 联系人邮箱

        Returns:
            bool: 联系人是否存在
        """
        session = self._get_session()
        try:
            count = session.query(Contact).filter(Contact.email == email).count()
            return count > 0
        except Exception as e:
            logger.error(f"检查联系人是否存在失败: {str(e)}")
            return False
        finally:
            session.close()

    def get_contact_count(self) -> int:
        """
        获取联系人总数

        Returns:
            int: 联系人数量
        """
        session = self._get_session()
        try:
            count = session.query(Contact).count()
            return count
        except Exception as e:
            logger.error(f"获取联系人数量失败: {str(e)}")
            return 0
        finally:
            session.close()


# 创建全局实例（延迟初始化）
_global_model: Optional[ContactsModel] = None


def get_contacts_model(db_path: Optional[str] = None) -> ContactsModel:
    """
    获取联系人模型实例（单例模式）

    Args:
        db_path: 数据库路径 (可选)

    Returns:
        ContactsModel: 联系人模型实例
    """
    global _global_model

    if _global_model is None:
        _global_model = ContactsModel(db_path)

    return _global_model


if __name__ == "__main__":
    """测试代码"""
    print("=== 测试联系人模型 ===\n")

    # 创建模型实例
    model = ContactsModel()

    # 测试添加联系人
    print("添加测试联系人...")
    contact1 = model.add_contact(
        name="张三",
        email="zhangsan@example.com",
        remark="大学同学"
    )
    if contact1:
        print(f"✓ 联系人添加成功: {contact1.name} (ID: {contact1.id})")
    else:
        print("✗ 联系人添加失败")

    contact2 = model.add_contact(
        name="李四",
        email="lisi@example.com",
        remark="高中同学"
    )
    if contact2:
        print(f"✓ 联系人添加成功: {contact2.name} (ID: {contact2.id})")
    else:
        print("✗ 联系人添加失败")

    contact3 = model.add_contact(
        name="王五",
        email="wangwu@test.com",
        remark="同事"
    )
    if contact3:
        print(f"✓ 联系人添加成功: {contact3.name} (ID: {contact3.id})")
    else:
        print("✗ 联系人添加失败")

    # 测试通过 ID 查询
    print("\n通过 ID 查询联系人...")
    if contact1:
        found = model.get_contact_by_id(contact1.id)
        if found:
            print(f"✓ 找到联系人: {found.name} ({found.email})")
        else:
            print("✗ 未找到联系人")

    # 测试通过邮箱查询
    print("\n通过邮箱查询联系人...")
    found = model.get_contact_by_email("lisi@example.com")
    if found:
        print(f"✓ 找到联系人: {found.name} (ID: {found.id})")
    else:
        print("✗ 未找到联系人")

    # 测试模糊搜索
    print("\n测试模糊搜索...")
    results = model.search_contacts(keyword="张")
    print(f"✓ 搜索 '张': 找到 {len(results)} 个联系人")
    for c in results:
        print(f"  - {c.name} ({c.email})")

    results = model.search_contacts(keyword="example.com")
    print(f"✓ 搜索 'example.com': 找到 {len(results)} 个联系人")
    for c in results:
        print(f"  - {c.name} ({c.email})")

    # 测试通过 ID 搜索
    if contact2:
        results = model.search_contacts(keyword=str(contact2.id))
        print(f"✓ 搜索 ID '{contact2.id}': 找到 {len(results)} 个联系人")
        for c in results:
            print(f"  - {c.name} ({c.email})")

    # 测试更新联系人
    print("\n更新联系人...")
    if contact1:
        success = model.update_contact(
            contact_id=contact1.id,
            name="张三丰",
            remark="太极拳传人"
        )
        if success:
            print(f"✓ 联系人已更新")
            # 验证更新
            updated = model.get_contact_by_id(contact1.id)
            print(f"  新姓名: {updated.name}, 新备注: {updated.remark}")
        else:
            print("✗ 更新失败")

    # 获取所有联系人
    print("\n获取所有联系人...")
    all_contacts = model.get_all_contacts()
    print(f"✓ 共有 {len(all_contacts)} 个联系人")
    for c in all_contacts:
        print(f"  - {c.name} ({c.email}) - 备注: {c.remark or '无'}")

    # 测试邮箱重复
    print("\n测试邮箱重复...")
    duplicate = model.add_contact(
        name="赵六",
        email="zhangsan@example.com"  # 已存在的邮箱
    )
    if duplicate:
        print("✗ 应该拒绝重复邮箱")
    else:
        print("✓ 正确拒绝了重复邮箱")

    # 清理测试数据
    print("\n清理测试数据...")
    all_contacts = model.get_all_contacts()
    for contact in all_contacts:
        model.delete_contact(contact.id)
    print(f"✓ 已删除 {len(all_contacts)} 个测试联系人")

    print("\n测试完成！")
