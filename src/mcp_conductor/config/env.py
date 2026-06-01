from __future__ import annotations

import os
import re

# 环境变量引用匹配模式：匹配 ${VAR_NAME} 格式的字符串
# 规则：变量名必须以字母或下划线开头，后续可以是字母、数字或下划线
# 示例：${GITHUB_TOKEN}、${HOME}、${MY_VAR_123}
_ENV_PATTERN = re.compile(r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}$")


def resolve_env_reference(value: str) -> str:
    """
    解析单个环境变量引用，将 ${VAR_NAME} 格式替换为实际的环境变量值。

    此函数用于配置文件中的环境变量占位符替换。只有当整个字符串完全符合
    ${VAR_NAME} 格式时才会进行替换，部分匹配不会处理（如 "prefix_${VAR}"
    会原样返回）。

    参数说明：
        value: 待解析的字符串，可能是普通字符串或 ${VAR_NAME} 格式

    返回值：
        - 如果 value 符合 ${VAR_NAME} 格式，返回对应环境变量的值
        - 如果不符合格式，原样返回 value

    异常：
        ValueError: 当引用的环境变量不存在或未设置时抛出

    使用场景：
        # 场景1：解析环境变量引用
        token = resolve_env_reference("${GITHUB_TOKEN}")
        # 返回：os.environ["GITHUB_TOKEN"] 的值

        # 场景2：普通字符串（非环境变量格式）
        result = resolve_env_reference("hello world")
        # 返回："hello world"（原样返回）

        # 场景3：部分匹配（不会被解析）
        result = resolve_env_reference("prefix_${VAR}")
        # 返回："prefix_${VAR}"（因为不是完全的 ${VAR} 格式）

        # 场景4：环境变量不存在
        try:
            result = resolve_env_reference("${NONEXISTENT_VAR}")
        except ValueError as e:
            print(e)  # "Missing required environment variable: NONEXISTENT_VAR"

        # 场景5：在配置加载中的应用
        config_value = "${DATABASE_URL}"
        actual_value = resolve_env_reference(config_value)
        # 连接到 actual_value...

    :param value: 待解析的字符串值
    :return: 解析后的字符串（环境变量值或原值）
    :raises ValueError: 当引用的环境变量不存在时
    """
    match = _ENV_PATTERN.match(value)
    if not match:
        return value
    name = match.group("name")
    try:
        return os.environ[name]
    except KeyError as exc:
        raise ValueError(f"Missing required environment variable: {name}") from exc


def resolve_env_mapping(values: dict[str, str]) -> dict[str, str]:
    """
    批量解析字典中的所有环境变量引用。

    对输入字典的每个值调用 resolve_env_reference()，常用于解析配置文件
    中的环境变量映射（如 MCP 服务器的 env 配置）。保持键不变，只替换值
    中的环境变量引用。

    参数说明：
        values: 键值对字典，值可能包含 ${VAR_NAME} 格式的环境变量引用

    返回值：
        新的字典，所有值都已被解析为实际的环境变量值

    异常：
        ValueError: 当任何一个引用的环境变量不存在时抛出

    使用场景：
        # 场景1：解析 MCP 服务器的环境变量配置
        config_env = {
            "GITHUB_TOKEN": "${GITHUB_TOKEN}",
            "API_KEY": "${API_KEY}",
            "DEBUG_MODE": "false"  # 普通字符串，原样保留
        }
        resolved = resolve_env_mapping(config_env)
        # 返回：{
        #     "GITHUB_TOKEN": "ghp_xxx...",  # 实际的环境变量值
        #     "API_KEY": "sk-xxx...",
        #     "DEBUG_MODE": "false"
        # }

        # 场景2：在配置文件加载中的应用
        # mcp-conductor.config.json:
        # {
        #   "mcpServers": {
        #     "github": {
        #       "env": {
        #         "GITHUB_TOKEN": "${GITHUB_TOKEN}"
        #       }
        #     }
        #   }
        # }
        #
        # 加载时：
        server_config = {...}  # 从 JSON 读取
        server_config["env"] = resolve_env_mapping(server_config["env"])

        # 场景3：批量解析多个环境变量
        env_vars = {
            "DB_HOST": "${DB_HOST}",
            "DB_PORT": "${DB_PORT}",
            "DB_PASSWORD": "${DB_PASSWORD}"
        }
        resolved = resolve_env_mapping(env_vars)
        # 所有一次性解析，任何一个缺失都会抛出 ValueError

        # 场景4：错误处理
        try:
            resolved = resolve_env_mapping({
                "TOKEN": "${MISSING_VAR}"
            })
        except ValueError as e:
            print(f"配置错误: {e}")
            # 输出：配置错误: Missing required environment variable: MISSING_VAR

    :param values: 包含环境变量引用的字典
    :return: 解析后的新字典
    :raises ValueError: 当任何引用的环境变量不存在时
    """
    return {key: resolve_env_reference(value) for key, value in values.items()}
