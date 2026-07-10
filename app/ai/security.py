"""Credential encryption, masking, endpoint validation, and error sanitization."""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


SECRET_PATTERN = re.compile(r"(?i)(?:sk|api[-_]?key)[-_A-Za-z0-9]{8,}")


class CredentialConfigurationError(RuntimeError):
    pass


def _fernet() -> Fernet:
    raw = (current_app.config.get("AI_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if not raw:
        raise CredentialConfigurationError("AI 凭据加密主密钥尚未配置。")
    try:
        return Fernet(raw.encode("utf-8"))
    except Exception as exc:
        raise CredentialConfigurationError("AI 凭据加密主密钥格式无效。") from exc


def credential_store_status() -> dict:
    try:
        _fernet()
        return {"ready": True, "message": "AI 凭据存储已就绪。"}
    except CredentialConfigurationError as exc:
        return {"ready": False, "message": str(exc)}


def encrypt_api_key(api_key: str) -> str:
    value = (api_key or "").strip()
    if len(value) < 8:
        raise ValueError("API Key 长度不足。")
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialConfigurationError("API Key 无法解密，请由管理员重新填写。") from exc


def mask_api_key(api_key: str) -> str:
    value = (api_key or "").strip()
    suffix = value[-4:] if len(value) >= 4 else "****"
    return f"••••••••{suffix}"


def sanitize_provider_error(error: Exception | str) -> str:
    text = str(error).replace("\r", " ").replace("\n", " ")
    text = SECRET_PATTERN.sub("[REDACTED]", text)
    text = re.sub(r"(?i)(authorization|bearer)\s*[:=]?\s*[^,;\s]+", r"\1 [REDACTED]", text)
    return text[:450] or "模型服务调用失败。"


def _is_disallowed_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not address.is_global


def validate_base_url(base_url: str, *, allow_private: bool | None = None) -> str:
    value = (base_url or "").strip().rstrip("/")
    parsed = urlparse(value)
    allow_private = (
        bool(current_app.config.get("AI_ALLOW_PRIVATE_ENDPOINTS"))
        if allow_private is None
        else allow_private
    )
    if parsed.scheme not in ({"https", "http"} if allow_private else {"https"}):
        raise ValueError("模型 Endpoint 必须使用 HTTPS。")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("模型 Endpoint 格式无效。")
    hostname = parsed.hostname.lower().rstrip(".")
    if not allow_private and (
        hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local")
    ):
        raise ValueError("模型 Endpoint 不允许指向本机或内网地址。")
    if not allow_private and _is_disallowed_ip(hostname):
        raise ValueError("模型 Endpoint 不允许指向内网或保留地址。")
    if not allow_private:
        try:
            for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM):
                if _is_disallowed_ip(item[4][0]):
                    raise ValueError("模型 Endpoint 解析到了内网或保留地址。")
        except socket.gaierror:
            # Saving an offline configuration is allowed; the explicit connection
            # test will surface DNS failures before the model can be enabled.
            pass
    return value

