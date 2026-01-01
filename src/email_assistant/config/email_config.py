"""
邮件配置管理模块
提供邮件服务配置加载、验证和管理功能
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import yaml

# 配置日志
logger = logging.getLogger(__name__)


class ConfigLoader:
    """通用配置加载器"""

    @staticmethod
    def load_yaml_config(config_path: str) -> Dict[str, Any]:
        """
        加载YAML配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            Dict: 配置内容

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML格式错误
            Exception: 其他加载错误
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"配置文件不存在: {config_path}")

            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            logger.info(f"配置文件加载成功: {config_path}")
            return config

        except yaml.YAMLError as e:
            logger.error(f"YAML格式错误: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            raise

    @staticmethod
    def validate_config_keys(config: Dict[str, Any], required_keys: list, section_name: str = "配置") -> None:
        """
        验证配置文件中的必要键

        Args:
            config: 配置字典
            required_keys: 必需的键列表
            section_name: 配置节名称，用于错误信息

        Raises:
            ValueError: 缺少必要的配置项
        """
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise ValueError(f"{section_name}缺少必要的配置项: {', '.join(missing_keys)}")


class EmailConfig:
    """邮件配置类"""

    def __init__(self, config_path: Optional[str] = None, config_section: str = "email"):
        """
        初始化邮件配置

        Args:
            config_path: 配置文件路径，默认为项目根目录下的config.yaml
            config_section: 配置文件中的邮件配置节名称，默认为'email'
        """
        self.config_path = config_path or self._get_default_config_path()
        self.config_section = config_section
        self.config = self._load_config()

    @staticmethod
    def _get_default_config_path() -> str:
        """获取默认配置文件路径"""
        # 从当前文件位置推算项目根目录
        current_dir = Path(__file__).parent
        project_root = current_dir.parent.parent.parent
        return str(project_root / 'config.yaml')

    def _load_config(self) -> Dict[str, Any]:
        """加载并验证配置文件"""
        try:
            # 加载配置文件
            config = ConfigLoader.load_yaml_config(self.config_path)

            # 验证顶级配置节
            ConfigLoader.validate_config_keys(
                config,
                [self.config_section, 'llm'],
                "配置文件"
            )

            # 验证邮件配置节
            email_config = config[self.config_section]
            ConfigLoader.validate_config_keys(
                email_config,
                ['email_sender', 'auth_code'],
                f"邮件配置({self.config_section})"
            )

            # 验证master配置节
            ConfigLoader.validate_config_keys(
                config,
                ['master'],
                "配置文件"
            )

            master_config = config['master']
            ConfigLoader.validate_config_keys(
                master_config,
                ['master_email', 'master_name'],
                "master配置"
            )

            logger.info("邮件配置加载成功")
            return config

        except Exception as e:
            logger.error(f"邮件配置加载失败: {str(e)}")
            raise

    def get_smtp_config(self) -> Dict[str, str]:
        """
        获取SMTP配置

        Returns:
            Dict: SMTP配置信息，包含服务器、端口、邮箱、授权码等
        """
        email_config = self.config[self.config_section]

        return {
            'smtp_server': email_config.get('smtp_server', 'smtp.qq.com'),
            'smtp_port': email_config.get('smtp_port', '587'),  # QQ邮箱推荐使用587端口
            'sender_email': email_config['email_sender'],
            'auth_code': email_config['auth_code'],
            'use_ssl': email_config.get('use_ssl', False),
            'use_tls': email_config.get('use_tls', True)
        }

    def get_imap_config(self) -> Dict[str, str]:
        """
        获取IMAP配置

        Returns:
            Dict: IMAP配置信息，包含服务器、端口、邮箱、授权码等
        """
        email_config = self.config[self.config_section]

        return {
            'imap_server': email_config.get('imap_server', 'imap.qq.com'),
            'imap_port': email_config.get('imap_port', '993'),  # QQ邮箱IMAP SSL端口
            'email': email_config['email_sender'],
            'auth_code': email_config['auth_code'],
        }

    def get_sender_info(self) -> Dict[str, str]:
        """
        获取发件人信息

        Returns:
            Dict: 发件人信息，包含邮箱和姓名
        """
        email_config = self.config[self.config_section]

        return {
            'email': email_config['email_sender'],
            'name': email_config.get('sender_name', '邮件助手'),
            'signature': email_config.get('signature', ''),
            'organization': email_config.get('organization', '')
        }

    def get_master_email(self) -> str:
        """
        直接获取master邮箱

        Returns:
            str: master的邮箱地址
        """
        return self.config['master']['master_email']

    def get_master_info(self) -> Dict[str, str]:
        """
        获取master信息

        Returns:
            Dict: master人信息，包含邮箱和姓名
        """
        master_config = self.config['master']

        return {
            'master_email': master_config['master_email'],
            'name': master_config.get('master_name', 'Ethan')
        }
    

    def get_reply_to_info(self) -> Optional[str]:
        """
        获取回复邮箱信息

        Returns:
            Optional[str]: 回复邮箱，如果未配置则返回None
        """
        email_config = self.config[self.config_section]
        return email_config.get('reply_to')

    def get_llm_config(self) -> Dict[str, Any]:
        """
        获取LLM配置

        Returns:
            Dict: LLM配置信息
        """
        return self.config.get('llm', {})

    def get_email_limits(self) -> Dict[str, Any]:
        """
        获取邮件发送限制配置

        Returns:
            Dict: 邮件限制配置，包含每日发送上限、附件大小限制等
        """
        email_config = self.config[self.config_section]

        return {
            'daily_limit': email_config.get('daily_limit', 100),
            'attachment_size_limit': email_config.get('attachment_size_limit', 25 * 1024 * 1024),  # 25MB
            'max_attachments': email_config.get('max_attachments', 10),
            'allowed_attachment_types': email_config.get('allowed_attachment_types', []),
            'blocked_attachment_types': email_config.get('blocked_attachment_types', ['.exe', '.bat', '.cmd'])
        }

    def get_retry_config(self) -> Dict[str, Any]:
        """
        获取重试配置

        Returns:
            Dict: 重试配置，包含重试次数、重试间隔等
        """
        email_config = self.config[self.config_section]

        return {
            'max_retries': email_config.get('max_retries', 3),
            'retry_delay': email_config.get('retry_delay', 1),  # 秒
            'retry_backoff_factor': email_config.get('retry_backoff_factor', 2)
        }

    def is_test_mode(self) -> bool:
        """
        检查是否为测试模式

        Returns:
            bool: 是否为测试模式
        """
        email_config = self.config[self.config_section]
        return email_config.get('test_mode', False)

    def get_test_recipients(self) -> list:
        """
        获取测试模式下的收件人列表

        Returns:
            list: 测试收件人列表
        """
        email_config = self.config[self.config_section]
        return email_config.get('test_recipients', [])

    def get_config_section(self, section_name: str) -> Dict[str, Any]:
        """
        获取配置文件中的任意节

        Args:
            section_name: 节名称

        Returns:
            Dict: 配置节内容，如果不存在则返回空字典
        """
        return self.config.get(section_name, {})

    def reload_config(self) -> None:
        """重新加载配置文件"""
        logger.info("重新加载配置文件...")
        self.config = self._load_config()
        logger.info("配置文件重新加载完成")

    def validate_config(self) -> Dict[str, Any]:
        """
        验证配置的完整性和正确性

        Returns:
            Dict: 验证结果，包含valid、errors、warnings等字段
        """
        errors = []
        warnings = []

        try:
            # 验证SMTP配置
            smtp_config = self.get_smtp_config()
            if not smtp_config['sender_email']:
                errors.append("发件人邮箱不能为空")
            if not smtp_config['auth_code']:
                errors.append("授权码不能为空")

            # 验证邮件限制
            limits = self.get_email_limits()
            if limits['daily_limit'] <= 0:
                warnings.append("每日发送限制设置过小")
            if limits['attachment_size_limit'] <= 0:
                warnings.append("附件大小限制设置过小")

            # 验证测试模式配置
            if self.is_test_mode() and not self.get_test_recipients():
                warnings.append("测试模式下未配置测试收件人")

        except Exception as e:
            errors.append(f"配置验证过程中发生错误: {str(e)}")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'smtp_config': self.get_smtp_config(),
            'sender_info': self.get_sender_info()
        }

    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要信息（隐藏敏感信息）

        Returns:
            Dict: 配置摘要
        """
        smtp_config = self.get_smtp_config()
        sender_info = self.get_sender_info()

        return {
            'config_path': self.config_path,
            'smtp_server': smtp_config['smtp_server'],
            'smtp_port': smtp_config['smtp_port'],
            'sender_email': smtp_config['sender_email'],
            'sender_name': sender_info['name'],
            'auth_code_configured': bool(smtp_config['auth_code']),
            'test_mode': self.is_test_mode(),
            'config_valid': self.validate_config()['valid']
        }


# 创建默认邮件配置实例
default_email_config = EmailConfig()


if __name__ == "__main__":
    # 测试代码
    import json

    print("测试邮件配置加载...")

    try:
        config = EmailConfig()

        print("\n配置摘要:")
        summary = config.get_config_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))

        print("\n配置验证结果:")
        validation = config.validate_config()
        print(json.dumps(validation, indent=2, ensure_ascii=False))

        print("\nSMTP配置:")
        smtp_config = config.get_smtp_config()
        print(json.dumps(smtp_config, indent=2, ensure_ascii=False))

        print("\n发件人信息:")
        sender_info = config.get_sender_info()
        print(json.dumps(sender_info, indent=2, ensure_ascii=False))

        print("\nmaster信息:")
        master_email = config.get_master_info().get('master_email')
        print(master_email)

    except Exception as e:
        print(f"配置加载失败: {str(e)}")