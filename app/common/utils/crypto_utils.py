from cryptography.fernet import Fernet

# Deterministic key for the project context (In production, this should be managed securely)
# Using a fixed key derived from a seed for consistency across app and tools
_KEY_SEED = b"VCC_DPT_SECURE_KEY_2026_FIXED"
# Pad to 32 bytes for url-safe base64 conversion simulation or just use a generated one
# I will use a hardcoded valid Fernet key.
_SECRET_KEY = b'wz7F9P1q2e3r4t5y6u7i8o9p0a1s2d3f4g5h6j7k8l9='

class DPTEncryptor:
    def __init__(self, key: bytes = None):
        self.key = key if key else _SECRET_KEY
        self.fernet = Fernet(self.key)

    def encrypt(self, data: str) -> bytes:
        return self.fernet.encrypt(data.encode('utf-8'))

    def decrypt(self, data: bytes) -> str:
        return self.fernet.decrypt(data).decode('utf-8')

# Singleton instance
dpt_encryptor = DPTEncryptor()

