"""
联系人服务
提供联系人的添加、编辑、查询、删除等业务逻辑
"""

import logging
from typing import Dict, Any, List, Optional, Union
from email_validator import validate_email, EmailNotValidError

from ..models  import ContactsModel, Contact, get_contacts_model

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ContactService:
    """
    联系人服务类
    提供联系人的业务逻辑层
    """

    def __init__(self, model: Optional[ContactsModel] = None):
        """
        初始化联系人服务

        Args:
            model: 联系人模型实例，默认使用单例
        """
        self.model = model if model else get_contacts_model()
        logger.info("联系人服务初始化完成")

    # ==================== 添加联系人 ====================

    def add_contact(
        self,
        name: str,
        email: str,
        remark: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        添加联系人

        Args:
            name: 联系人姓名
            email: 联系人邮箱
            remark: 备注（可选）

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - data: Optional[Dict] - 联系人数据（成功时）
        """
        try:
            # 1. 验证姓名
            if not name or not name.strip():
                return {
                    "success": False,
                    "message": "联系人姓名不能为空",
                    "data": None
                }

            name = name.strip()

            if len(name) > 100:
                return {
                    "success": False,
                    "message": "联系人姓名长度不能超过100个字符",
                    "data": None
                }

            # 2. 验证邮箱
            if not email or not email.strip():
                return {
                    "success": False,
                    "message": "邮箱地址不能为空",
                    "data": None
                }

            email = email.strip()

            try:
                # 使用 email_validator 验证邮箱格式（不检查 DNS 可投递性）
                valid = validate_email(email, check_deliverability=False)
                email = valid.email  # 使用规范化后的邮箱
            except EmailNotValidError as e:
                return {
                    "success": False,
                    "message": f"邮箱格式不正确: {str(e)}",
                    "data": None
                }

            # 3. 验证备注长度
            if remark and len(remark) > 500:
                return {
                    "success": False,
                    "message": "备注长度不能超过500个字符",
                    "data": None
                }

            # 4. 检查邮箱是否已存在
            if self.model.contact_exists(email):
                return {
                    "success": False,
                    "message": f"邮箱 {email} 已存在",
                    "data": None
                }

            # 5. 添加联系人
            contact = self.model.add_contact(
                name=name,
                email=email,
                remark=remark.strip() if remark else None
            )

            if contact:
                logger.info(f"添加联系人成功: {name} ({email})")
                return {
                    "success": True,
                    "message": "联系人添加成功",
                    "data": contact.to_dict()
                }
            else:
                return {
                    "success": False,
                    "message": "添加联系人失败",
                    "data": None
                }

        except Exception as e:
            logger.error(f"添加联系人时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"添加联系人时发生错误: {str(e)}",
                "data": None
            }

    def batch_add_contacts(self, contacts_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量添加联系人

        Args:
            contacts_data: 联系人数据列表
                每个元素包含: name, email, remark (可选)

        Returns:
            Dict: 操作结果
                - success: bool - 是否全部成功
                - message: str - 提示信息
                - total: int - 总数
                - success_count: int - 成功数量
                - failed_count: int - 失败数量
                - results: List[Dict] - 详细结果
        """
        if not contacts_data:
            return {
                "success": False,
                "message": "联系人数据不能为空",
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "results": []
            }

        total = len(contacts_data)
        success_count = 0
        failed_count = 0
        results = []

        for idx, contact_data in enumerate(contacts_data):
            name = contact_data.get('name')
            email = contact_data.get('email')
            remark = contact_data.get('remark')

            result = self.add_contact(name, email, remark)
            results.append({
                "index": idx,
                "name": name,
                "email": email,
                "result": result
            })

            if result['success']:
                success_count += 1
            else:
                failed_count += 1

        all_success = failed_count == 0

        logger.info(
            f"批量添加联系人完成: 总数 {total}, "
            f"成功 {success_count}, 失败 {failed_count}"
        )

        return {
            "success": all_success,
            "message": f"批量添加完成: 成功 {success_count} 个, 失败 {failed_count} 个",
            "total": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }

    # ==================== 编辑联系人 ====================

    def update_contact(
        self,
        contact_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        remark: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        更新联系人信息

        Args:
            contact_id: 联系人 ID
            name: 新姓名（可选）
            email: 新邮箱（可选）
            remark: 新备注（可选）

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - data: Optional[Dict] - 更新后的联系人数据
        """
        try:
            # 1. 验证联系人是否存在
            contact = self.model.get_contact_by_id(contact_id)
            if not contact:
                return {
                    "success": False,
                    "message": f"联系人不存在 (ID: {contact_id})",
                    "data": None
                }

            # 2. 验证姓名
            if name is not None:
                if not name or not name.strip():
                    return {
                        "success": False,
                        "message": "联系人姓名不能为空",
                        "data": None
                    }
                name = name.strip()
                if len(name) > 100:
                    return {
                        "success": False,
                        "message": "联系人姓名长度不能超过100个字符",
                        "data": None
                    }

            # 3. 验证邮箱
            if email is not None:
                if not email or not email.strip():
                    return {
                        "success": False,
                        "message": "邮箱地址不能为空",
                        "data": None
                    }

                email = email.strip()

                try:
                    valid = validate_email(email, check_deliverability=False)
                    email = valid.email
                except EmailNotValidError as e:
                    return {
                        "success": False,
                        "message": f"邮箱格式不正确: {str(e)}",
                        "data": None
                    }

            # 4. 验证备注长度
            if remark is not None and len(remark) > 500:
                return {
                    "success": False,
                    "message": "备注长度不能超过500个字符",
                    "data": None
                }

            # 5. 更新联系人
            success = self.model.update_contact(
                contact_id=contact_id,
                name=name,
                email=email,
                remark=remark.strip() if remark else None
            )

            if success:
                # 获取更新后的数据
                updated_contact = self.model.get_contact_by_id(contact_id)
                logger.info(f"更新联系人成功: ID={contact_id}")
                return {
                    "success": True,
                    "message": "联系人更新成功",
                    "data": updated_contact.to_dict() if updated_contact else None
                }
            else:
                return {
                    "success": False,
                    "message": "更新联系人失败",
                    "data": None
                }

        except Exception as e:
            logger.error(f"更新联系人时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"更新联系人时发生错误: {str(e)}",
                "data": None
            }

    # ==================== 查询联系人 ====================

    def get_contact_by_id(self, contact_id: int) -> Dict[str, Any]:
        """
        根据 ID 获取联系人

        Args:
            contact_id: 联系人 ID

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - data: Optional[Dict] - 联系人数据
        """
        try:
            contact = self.model.get_contact_by_id(contact_id)

            if contact:
                return {
                    "success": True,
                    "message": "获取联系人成功",
                    "data": contact.to_dict()
                }
            else:
                return {
                    "success": False,
                    "message": f"联系人不存在 (ID: {contact_id})",
                    "data": None
                }

        except Exception as e:
            logger.error(f"获取联系人时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"获取联系人时发生错误: {str(e)}",
                "data": None
            }

    def get_contact_by_email(self, email: str) -> Dict[str, Any]:
        """
        根据邮箱获取联系人

        Args:
            email: 联系人邮箱

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - data: Optional[Dict] - 联系人数据
        """
        try:
            if not email or not email.strip():
                return {
                    "success": False,
                    "message": "邮箱地址不能为空",
                    "data": None
                }

            email = email.strip()
            contact = self.model.get_contact_by_email(email)

            if contact:
                return {
                    "success": True,
                    "message": "获取联系人成功",
                    "data": contact.to_dict()
                }
            else:
                return {
                    "success": False,
                    "message": f"联系人不存在 (邮箱: {email})",
                    "data": None
                }

        except Exception as e:
            logger.error(f"获取联系人时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"获取联系人时发生错误: {str(e)}",
                "data": None
            }

    def search_contacts(
        self,
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        email: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        搜索联系人

        Args:
            keyword: 关键字（在 id、name、email 中搜索）
            name: 姓名关键字（模糊匹配）
            email: 邮箱关键字（模糊匹配）
            limit: 返回结果数量限制

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - count: int - 结果数量
                - data: List[Dict] - 联系人列表
        """
        try:
            contacts = self.model.search_contacts(
                keyword=keyword,
                name=name,
                email=email,
                limit=limit
            )

            return {
                "success": True,
                "message": f"找到 {len(contacts)} 个联系人",
                "count": len(contacts),
                "data": [contact.to_dict() for contact in contacts]
            }

        except Exception as e:
            logger.error(f"搜索联系人时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"搜索联系人时发生错误: {str(e)}",
                "count": 0,
                "data": []
            }

    def get_all_contacts(self, limit: int = 1000) -> Dict[str, Any]:
        """
        获取所有联系人

        Args:
            limit: 返回结果数量限制

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - count: int - 结果数量
                - data: List[Dict] - 联系人列表
        """
        try:
            contacts = self.model.get_all_contacts(limit=limit)

            return {
                "success": True,
                "message": f"获取成功，共 {len(contacts)} 个联系人",
                "count": len(contacts),
                "data": [contact.to_dict() for contact in contacts]
            }

        except Exception as e:
            logger.error(f"获取联系人列表时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"获取联系人列表时发生错误: {str(e)}",
                "count": 0,
                "data": []
            }

    def get_contact_count(self) -> Dict[str, Any]:
        """
        获取联系人总数

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - count: int - 联系人数量
        """
        try:
            count = self.model.get_contact_count()

            return {
                "success": True,
                "message": "获取成功",
                "count": count
            }

        except Exception as e:
            logger.error(f"获取联系人数量时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"获取联系人数量时发生错误: {str(e)}",
                "count": 0
            }

    # ==================== 删除联系人 ====================

    def delete_contact(self, contact_id: int) -> Dict[str, Any]:
        """
        删除联系人

        Args:
            contact_id: 联系人 ID

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
        """
        try:
            # 先获取联系人信息（用于日志）
            contact = self.model.get_contact_by_id(contact_id)

            if not contact:
                return {
                    "success": False,
                    "message": f"联系人不存在 (ID: {contact_id})"
                }

            contact_name = contact.name
            contact_email = contact.email

            # 删除联系人
            success = self.model.delete_contact(contact_id)

            if success:
                logger.info(f"删除联系人成功: {contact_name} ({contact_email})")
                return {
                    "success": True,
                    "message": "联系人删除成功"
                }
            else:
                return {
                    "success": False,
                    "message": "删除联系人失败"
                }

        except Exception as e:
            logger.error(f"删除联系人时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"删除联系人时发生错误: {str(e)}"
            }

    def batch_delete_contacts(self, contact_ids: List[int]) -> Dict[str, Any]:
        """
        批量删除联系人

        Args:
            contact_ids: 联系人 ID 列表

        Returns:
            Dict: 操作结果
                - success: bool - 是否全部成功
                - message: str - 提示信息
                - total: int - 总数
                - success_count: int - 成功数量
                - failed_count: int - 失败数量
                - results: List[Dict] - 详细结果
        """
        if not contact_ids:
            return {
                "success": False,
                "message": "联系人 ID 列表不能为空",
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "results": []
            }

        total = len(contact_ids)
        success_count = 0
        failed_count = 0
        results = []

        for contact_id in contact_ids:
            result = self.delete_contact(contact_id)
            results.append({
                "contact_id": contact_id,
                "result": result
            })

            if result['success']:
                success_count += 1
            else:
                failed_count += 1

        all_success = failed_count == 0

        logger.info(
            f"批量删除联系人完成: 总数 {total}, "
            f"成功 {success_count}, 失败 {failed_count}"
        )

        return {
            "success": all_success,
            "message": f"批量删除完成: 成功 {success_count} 个, 失败 {failed_count} 个",
            "total": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }

    # ==================== 工具方法 ====================

    def contact_exists(self, email: str) -> Dict[str, Any]:
        """
        检查邮箱是否存在

        Args:
            email: 邮箱地址

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - exists: bool - 邮箱是否存在
        """
        try:
            if not email or not email.strip():
                return {
                    "success": False,
                    "message": "邮箱地址不能为空",
                    "exists": False
                }

            email = email.strip()
            exists = self.model.contact_exists(email)

            return {
                "success": True,
                "message": "检查完成",
                "exists": exists
            }

        except Exception as e:
            logger.error(f"检查邮箱是否存在时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"检查邮箱时发生错误: {str(e)}",
                "exists": False
            }

    def export_contacts(self, format: str = "dict") -> Dict[str, Any]:
        """
        导出所有联系人

        Args:
            format: 导出格式 (dict/json/list)

        Returns:
            Dict: 操作结果
                - success: bool - 是否成功
                - message: str - 提示信息
                - count: int - 联系人数量
                - data: Any - 导出的数据
        """
        try:
            result = self.get_all_contacts(limit=10000)

            if not result['success']:
                return result

            data = result['data']

            if format == "json":
                import json
                return {
                    "success": True,
                    "message": "导出成功",
                    "count": len(data),
                    "data": json.dumps(data, ensure_ascii=False, indent=2)
                }
            else:
                return result

        except Exception as e:
            logger.error(f"导出联系人时发生错误: {str(e)}")
            return {
                "success": False,
                "message": f"导出联系人时发生错误: {str(e)}",
                "count": 0,
                "data": None
            }


# 创建全局服务实例（单例模式）
_global_service: Optional[ContactService] = None


def get_contact_service() -> ContactService:
    """
    获取联系人服务实例（单例模式）

    Returns:
        ContactService: 联系人服务实例
    """
    global _global_service

    if _global_service is None:
        _global_service = ContactService()

    return _global_service


if __name__ == "__main__":
    """测试代码"""
    import sys
    from pathlib import Path

    # 添加项目根目录到 Python 路径
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

    # 重新导入模块（因为需要正确的路径）
    import importlib
    import src.email_assistant.service.contact_service as contact_service_module
    importlib.reload(contact_service_module)

    from src.email_assistant.service.contact_service import ContactService

    print("=== 测试联系人服务 ===\n")

    # 创建服务实例
    service = ContactService()

    # 测试添加联系人
    print("1. 测试添加联系人")
    print("-" * 50)
    result = service.add_contact(
        name="张三",
        email="zhangsan@example.com",
        remark="测试联系人"
    )
    print(f"添加结果: {result}")
    print()

    # 测试查询联系人
    if result['success']:
        contact_id = result['data']['id']

        print("2. 测试查询联系人")
        print("-" * 50)
        result = service.get_contact_by_id(contact_id)
        print(f"查询结果: {result}")
        print()

        # 测试更新联系人
        print("3. 测试更新联系人")
        print("-" * 50)
        result = service.update_contact(
            contact_id=contact_id,
            name="张三丰",
            remark="已更新备注"
        )
        print(f"更新结果: {result}")
        print()

        # 测试搜索联系人
        print("4. 测试搜索联系人")
        print("-" * 50)
        result = service.search_contacts(keyword="张")
        print(f"搜索结果: 找到 {result['count']} 个")
        print()

        # 测试获取所有联系人
        print("5. 测试获取所有联系人")
        print("-" * 50)
        result = service.get_all_contacts()
        print(f"获取结果: {result['count']} 个联系人")
        print()

        # 测试删除联系人
        print("6. 测试删除联系人")
        print("-" * 50)
        result = service.delete_contact(contact_id)
        print(f"删除结果: {result}")
        print()

    # 测试批量操作
    print("7. 测试批量添加联系人")
    print("-" * 50)
    batch_data = [
        {"name": "李四", "email": "lisi@example.com"},
        {"name": "王五", "email": "wangwu@example.com"},
        {"name": "赵六", "email": "zhaoliu@example.com"}
    ]
    result = service.batch_add_contacts(batch_data)
    print(f"批量添加: {result['message']}")
    print()

    # 清理测试数据
    print("8. 清理测试数据")
    print("-" * 50)
    result = service.get_all_contacts()
    for contact in result['data']:
        service.delete_contact(contact['id'])
    print(f"已清理 {result['count']} 个测试联系人")

    print("\n测试完成！")
