from __future__ import annotations

import logging

"""
✅ 全局生效：
configure_logging() 在程序启动时调用一次
配置的格式和级别应用于整个项目的所有日志输出
任何模块使用 logging.getLogger() 都会自动遵循这个配置
✅ 配置位置合理：
在 main() 的早期调用
在创建 GatewayRuntime 和启动服务器之前
确保后续所有代码的日志都能正确输出
这就是为什么只需要在 CLI 入口调用一次 configure_logging()，整个项目的日志就都能正常工作了！🎯
"""


def configure_logging(level: str = "INFO") -> None:
    """
    这段代码配置 Python 日志系统：
    设置日志级别（将字符串转换为 logging 常量，如 INFO、DEBUG）
    定义日志格式：时间戳 + 级别 + 模块名 + 消息
    使用 getattr 安全获取级别，无效时降级为 INFO
    :param level:
    :return:
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
