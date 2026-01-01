"""
联系人工具
提供联系人的查询和添加功能，集成到 LangChain 工具系统
"""

import logging
from typing import Dict, Any, List, Union, Optional
from langchain.tools import tool

from ..service import ContactService, get_contact_service

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 获取联系人服务实例
contact_service = get_contact_service()


class ContactTool:
    """
    联系人工具类
    提供联系人的查询和添加功能
    """

    @staticmethod
    @tool
    def search_contact(
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        搜索联系人工具，支持通过姓名或邮箱进行模糊查询

        当需要在通讯录中查找联系人时，使用此工具。可以通过关键字、姓名或邮箱进行搜索。

        参数说明：
            keyword: 搜索关键字（可选）
                - 可以是联系人 ID（精确匹配）
                - 可以是姓名的一部分（模糊匹配）
                - 可以是邮箱的一部分（模糊匹配）
                - 优先使用此参数进行全局搜索

            name: 姓名关键字（可选）
                - 仅在姓名中搜索
                - 支持模糊匹配

            email: 邮箱关键字（可选）
                - 仅在邮箱中搜索
                - 支持模糊匹配

        使用示例：
            # 通过姓名搜索
            search_contact(name="张三")

            # 通过邮箱搜索
            search_contact(email="qq.com")

            # 通过关键字搜索（推荐）
            search_contact(keyword="张")

            # 组合搜索
            search_contact(name="张", email="qq.com")

        返回值：
            Dict: 搜索结果
                - success: 是否成功
                - message: 提示信息
                - count: 找到的联系人数量
                - data: 联系人列表，每个联系人包含：
                    - id: 联系人 ID
                    - name: 姓名
                    - email: 邮箱
                    - remark: 备注
                    - created_at: 创建时间
                    - updated_at: 更新时间
        """
        try:
            logger.info(f"开始搜索联系人 - keyword: {keyword}, name: {name}, email: {email}")
            print(f"🔍 搜索联系人 - 关键字: {keyword}, 姓名: {name}, 邮箱: {email}")

            # 调用服务层进行搜索
            result = contact_service.search_contacts(
                keyword=keyword,
                name=name,
                email=email,
                limit=100
            )

            if result['success']:
                count = result['count']
                contacts = result['data']

                # 格式化输出
                if count > 0:
                    print(f"✓ 找到 {count} 个联系人：")
                    for contact in contacts:
                        print(f"  [{contact['id']}] {contact['name']} - {contact['email']}")
                        if contact.get('remark'):
                            print(f"       备注: {contact['remark']}")
                else:
                    print("⚠️  未找到匹配的联系人")

                logger.info(f"搜索完成，找到 {count} 个联系人")
                return {
                    'success': True,
                    'message': f"找到 {count} 个联系人",
                    'count': count,
                    'contacts': contacts
                }
            else:
                logger.warning(f"搜索失败: {result['message']}")
                return {
                    'success': False,
                    'message': result['message'],
                    'count': 0,
                    'contacts': []
                }

        except Exception as e:
            error_msg = f"搜索联系人时发生错误: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return {
                'success': False,
                'message': error_msg,
                'count': 0,
                'contacts': []
            }

    @staticmethod
    @tool
    def add_contact(
        contacts: Union[str, List[Dict[str, Any]], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        添加联系人工具，支持添加单个或多个联系人到通讯录

        当需要添加新联系人到通讯录时使用此工具。支持单个添加和批量添加。

        参数说明：
            contacts: 联系人信息，支持多种格式：

            方式1 - 字符串格式（单个联系人，推荐用于 LLM 调用）：
                "姓名,邮箱地址"
                "姓名,邮箱地址,备注"

                示例：
                - add_contact(contacts="张三,zhangsan@example.com")
                - add_contact(contacts="张三,zhangsan@example.com,大学同学")

            方式2 - 字典格式（单个联系人）：
                {
                    "name": "张三",
                    "email": "zhangsan@example.com",
                    "remark": "大学同学"  # 可选
                }

            方式3 - 列表格式（批量添加多个联系人）：
                [
                    {"name": "张三", "email": "zhangsan@example.com"},
                    {"name": "李四", "email": "lisi@example.com", "remark": "高中同学"}
                ]

        字段说明：
            name: 联系人姓名（必填）
            email: 联系人邮箱（必填）
            remark: 联系人备注（可选）

        验证规则：
            - 姓名不能为空，长度不超过 100 字符
            - 邮箱格式必须正确
            - 邮箱必须唯一（不能重复）
            - 备注长度不超过 500 字符

        使用示例：
            # 添加单个联系人（字符串格式）
            add_contact(contacts="张三,zhangsan@example.com")

            # 添加单个联系人（带备注）
            add_contact(contacts="张三,zhangsan@example.com,大学同学")

            # 批量添加联系人
            add_contact(contacts=[
                {"name": "张三", "email": "zhangsan@example.com"},
                {"name": "李四", "email": "lisi@example.com", "remark": "同事"}
            ])

        返回值：
            Dict: 添加结果
                - success: 是否全部成功
                - message: 详细信息
                - total: 总数
                - success_count: 成功数量
                - failed_count: 失败数量
                - data: 添加成功的联系人列表
        """
        try:
            logger.info(f"开始添加联系人: {contacts}")
            print(f"📝 添加联系人: {contacts}")

            # 处理不同格式的输入
            contacts_list = []

            # 格式1: 字符串格式 "姓名,邮箱,备注"
            if isinstance(contacts, str):
                parts = [p.strip() for p in contacts.split(',')]
                if len(parts) < 2:
                    return {
                        'success': False,
                        'message': "字符串格式错误，应为 '姓名,邮箱' 或 '姓名,邮箱,备注'",
                        'total': 0,
                        'success_count': 0,
                        'failed_count': 1
                    }

                contact_data = {
                    'name': parts[0],
                    'email': parts[1],
                    'remark': parts[2] if len(parts) > 2 else None
                }
                contacts_list = [contact_data]

            # 格式2: 单个字典
            elif isinstance(contacts, dict):
                contacts_list = [contacts]

            # 格式3: 列表
            elif isinstance(contacts, list):
                contacts_list = contacts

            else:
                return {
                    'success': False,
                    'message': f"不支持的参数类型: {type(contacts)}",
                    'total': 0,
                    'success_count': 0,
                    'failed_count': 0
                }

            # 验证必填字段
            for idx, contact in enumerate(contacts_list):
                if 'name' not in contact or not contact['name']:
                    return {
                        'success': False,
                        'message': f"第 {idx + 1} 个联系人缺少姓名字段",
                        'total': len(contacts_list),
                        'success_count': 0,
                        'failed_count': len(contacts_list)
                    }

                if 'email' not in contact or not contact['email']:
                    return {
                        'success': False,
                        'message': f"第 {idx + 1} 个联系人缺少邮箱字段",
                        'total': len(contacts_list),
                        'success_count': 0,
                        'failed_count': len(contacts_list)
                    }

            # 调用服务层批量添加
            result = contact_service.batch_add_contacts(contacts_list)

            # 格式化输出
            total = result['total']
            success_count = result['success_count']
            failed_count = result['failed_count']

            if failed_count == 0:
                print(f"✅ 成功添加 {success_count} 个联系人")
                for contact in result.get('results', []):
                    if contact['result']['success']:
                        data = contact['result']['data']
                        print(f"  - {data['name']} ({data['email']})")
            else:
                print(f"⚠️  部分成功: 成功 {success_count} 个，失败 {failed_count} 个")

                # 显示失败的详情
                for contact in result.get('results', []):
                    if not contact['result']['success']:
                        print(f"  ❌ {contact['name']} - {contact['result']['message']}")

            logger.info(f"添加完成 - 总数: {total}, 成功: {success_count}, 失败: {failed_count}")

            return {
                'success': result['success'],
                'message': result['message'],
                'total': total,
                'success_count': success_count,
                'failed_count': failed_count,
                'data': [r['result']['data'] for r in result.get('results', [])
                        if r['result']['success']]
            }

        except Exception as e:
            error_msg = f"添加联系人时发生错误: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return {
                'success': False,
                'message': error_msg,
                'total': 0,
                'success_count': 0,
                'failed_count': 0
            }


# 导出工具实例，方便 LangChain 使用
search_contact_tool = ContactTool.search_contact
add_contact_tool = ContactTool.add_contact

