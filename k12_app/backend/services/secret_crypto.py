# k12_app/services/secret_crypto.py
"""敏感字段加解密（S-08）— 企微 CorpSecret 等存储前加密、读取时解密。

使用 Fernet 对称加密，密钥来自 settings.SECRET_ENCRYPTION_KEY。
解密时对历史明文数据做兼容（非 Fernet token 原样返回）。
"""

from cryptography.fernet import Fernet, InvalidToken

from k12_app.backend.config import settings

_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.SECRET_ENCRYPTION_KEY.encode("utf-8"))
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    """加密敏感字段。空值原样返回。"""
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """解密敏感字段。空值或历史明文数据原样返回。"""
    if not value:
        return value
    try:
        return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # 兼容加密改造前已入库的明文数据
        return value
