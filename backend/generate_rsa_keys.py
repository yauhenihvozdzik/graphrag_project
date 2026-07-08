"""Генерация RSA-ключей для JWT RS256."""
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import os


def main():
    os.makedirs("keys", exist_ok=True)

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Приватный ключ
    with open("keys/private.pem", "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Публичный ключ
    with open("keys/public.pem", "wb") as f:
        f.write(key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

    print("✅ RSA-ключи сгенерированы: keys/private.pem, keys/public.pem")


if __name__ == "__main__":
    main()
