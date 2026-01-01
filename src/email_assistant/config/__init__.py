"""
配置模块
提供应用程序配置管理功能
"""

from .email_config import EmailConfig, ConfigLoader

__all__ = ['EmailConfig', 'ConfigLoader']