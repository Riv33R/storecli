"""
ssh_client.py — Модуль для выполнения команд на удалённом сервере по SSH.

Используется библиотека Paramiko для безопасного подключения.
Поддерживается аутентификация по SSH-ключу и по паролю.
"""

import logging

import paramiko

from app.config import SSHConfig

logger = logging.getLogger(__name__)


class SSHConnectionError(Exception):
    """Ошибка подключения к удалённому серверу по SSH."""


class SSHCommandError(Exception):
    """Ошибка выполнения команды на удалённом сервере."""


def execute_remote_command(config: SSHConfig, command: str) -> str:
    """
    Подключается к удалённому серверу по SSH и выполняет команду.

    Args:
        config: Конфигурация SSH-подключения.
        command: Команда для выполнения на удалённом сервере.

    Returns:
        Строка с выводом (stdout) выполненной команды.

    Raises:
        SSHConnectionError: Если не удалось подключиться к серверу.
        SSHCommandError: Если команда завершилась с ошибкой.
    """
    client = paramiko.SSHClient()

    # Автоматически добавляем неизвестные хосты (для первого подключения)
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Формируем параметры подключения
        connect_kwargs = {
            "hostname": config.host,
            "port": config.port,
            "username": config.user,
            "timeout": config.timeout,
        }

        # Выбираем метод аутентификации
        if config.auth_method == "key":
            if config.key_path:
                connect_kwargs["key_filename"] = config.key_path
            if config.key_passphrase:
                connect_kwargs["passphrase"] = config.key_passphrase
            logger.info(
                "Подключение к %s:%d по SSH-ключу (user: %s)",
                config.host,
                config.port,
                config.user,
            )
        else:
            connect_kwargs["password"] = config.password
            logger.info(
                "Подключение к %s:%d по паролю (user: %s)",
                config.host,
                config.port,
                config.user,
            )

        client.connect(**connect_kwargs)
        logger.info("SSH-подключение установлено успешно")

        # Выполняем команду
        logger.info("Выполнение команды: %s", command)
        stdin, stdout, stderr = client.exec_command(command, timeout=config.timeout)

        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", errors="replace")
        error_output = stderr.read().decode("utf-8", errors="replace")

        if exit_code != 0:
            logger.error(
                "Команда завершилась с кодом %d: %s", exit_code, error_output
            )
            raise SSHCommandError(
                f"Команда завершилась с кодом {exit_code}. "
                f"Stderr: {error_output.strip()}"
            )

        logger.info("Команда выполнена успешно (exit code: 0)")
        return output

    except paramiko.AuthenticationException as exc:
        msg = f"Ошибка аутентификации SSH для {config.user}@{config.host}: {exc}"
        logger.error(msg)
        raise SSHConnectionError(msg) from exc

    except paramiko.SSHException as exc:
        msg = f"Ошибка SSH-протокола при подключении к {config.host}: {exc}"
        logger.error(msg)
        raise SSHConnectionError(msg) from exc

    except OSError as exc:
        msg = f"Сервер {config.host}:{config.port} недоступен: {exc}"
        logger.error(msg)
        raise SSHConnectionError(msg) from exc

    finally:
        client.close()
        logger.debug("SSH-соединение закрыто")
