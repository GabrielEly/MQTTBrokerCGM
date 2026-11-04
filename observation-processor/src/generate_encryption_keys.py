import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_key_pair(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    private_path = directory / "private.pem"
    public_path = directory / "public.pem"
    if private_path.exists() or public_path.exists():
        raise FileExistsError(
            f"Encryption key files already exist in {directory}; refusing to overwrite"
        )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    with private_path.open("xb") as private_file:
        private_file.write(private_bytes)
    with public_path.open("xb") as public_file:
        public_file.write(public_bytes)
    if os.name != "nt":
        os.chmod(private_path, 0o600)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: generate_encryption_keys.py <output-directory>")
    generate_key_pair(Path(sys.argv[1]))
    print(f"Generated public and private keys in {sys.argv[1]}")
