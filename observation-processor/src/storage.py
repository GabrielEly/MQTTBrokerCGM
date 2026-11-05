import base64
import json
import os
from pathlib import Path
from typing import Any

import psycopg
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_ENVELOPE_VERSION = 1
_ENVELOPE_AAD = b"observation-envelope-v1"


def encrypt_observation(
    observation: dict[str, Any],
    public_key_path: Path,
) -> bytes:
    public_key = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("The observations public key must be an RSA key")
    if public_key.key_size < 2048:
        raise ValueError("The RSA public key must be at least 2048 bits")

    plaintext = json.dumps(
        observation,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    encrypted_observation = AESGCM(data_key).encrypt(
        nonce,
        plaintext,
        _ENVELOPE_AAD,
    )
    encrypted_key = public_key.encrypt(
        data_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    envelope = {
        "version": _ENVELOPE_VERSION,
        "algorithm": "RSA-OAEP-256+A256GCM",
        "encrypted_key": base64.b64encode(encrypted_key).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(encrypted_observation).decode("ascii"),
    }
    return json.dumps(envelope, separators=(",", ":")).encode("ascii")


def decrypt_observation(
    encrypted_payload: bytes,
    private_key_path: Path,
) -> dict[str, Any]:
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(),
        password=None,
    )
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError("The observations private key must be an RSA key")

    envelope = json.loads(encrypted_payload)
    if not isinstance(envelope, dict):
        raise ValueError("Invalid encrypted observation envelope")
    if (
        envelope.get("version") != _ENVELOPE_VERSION
        or envelope.get("algorithm") != "RSA-OAEP-256+A256GCM"
    ):
        raise ValueError("Unsupported encrypted observation format")

    data_key = private_key.decrypt(
        base64.b64decode(envelope["encrypted_key"], validate=True),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    plaintext = AESGCM(data_key).decrypt(
        base64.b64decode(envelope["nonce"], validate=True),
        base64.b64decode(envelope["ciphertext"], validate=True),
        _ENVELOPE_AAD,
    )
    return json.loads(plaintext)


def ensure_schema(database_connection: dict[str, Any]) -> None:
    with psycopg.connect(**database_connection) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS observation_references (
                observation_id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                cid TEXT NOT NULL UNIQUE,
                observed_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def store_observation(
    observation: dict[str, Any],
    database_connection: dict[str, Any],
    ipfs_api_url: str,
    public_key_path: Path,
) -> str:
    observation_id = observation["id"]
    patient_reference = observation["subject"]["reference"]
    if patient_reference.startswith("urn:uuid:"):
        patient_id = patient_reference[len("urn:uuid:") :]
    elif patient_reference.startswith("Patient/"):
        patient_id = patient_reference[len("Patient/") :]
    else:
        raise ValueError(f"Unsupported patient reference: {patient_reference}")
    if not patient_id:
        raise ValueError("Observation patient reference must include an ID")

    with psycopg.connect(**database_connection) as connection:
        existing = connection.execute(
            "SELECT cid FROM observation_references WHERE observation_id = %s",
            (observation_id,),
        ).fetchone()
        if existing:
            return existing[0]

        encrypted_payload = encrypt_observation(observation, public_key_path)
        response = requests.post(
            f"{ipfs_api_url.rstrip('/')}/api/v0/add",
            params={"pin": "true"},
            files={
                "file": (
                    "observation.enc",
                    encrypted_payload,
                    "application/octet-stream",
                )
            },
            timeout=(5, 30),
        )
        response.raise_for_status()
        result = response.json()
        cid = result.get("Hash")
        if not isinstance(cid, str) or not cid:
            raise ValueError("IPFS add response did not contain a CID")

        connection.execute(
            """
            INSERT INTO observation_references
                (observation_id, patient_id, cid, observed_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (observation_id) DO NOTHING
            """,
            (
                observation_id,
                patient_id,
                cid,
                observation["effectiveDateTime"],
            ),
        )
    return cid


def get_patient_observations(
    patient_id: str,
    database_connection: dict[str, Any],
    ipfs_api_url: str,
    private_key_path: Path,
) -> list[dict[str, Any]]:
    with psycopg.connect(**database_connection) as connection:
        references = connection.execute(
            """
            SELECT cid
            FROM observation_references
            WHERE patient_id = %s
            ORDER BY observed_at, observation_id
            """,
            (patient_id,),
        ).fetchall()

    observations = []
    for (cid,) in references:
        response = requests.post(
            f"{ipfs_api_url.rstrip('/')}/api/v0/cat",
            params={"arg": cid},
            timeout=(5, 30),
        )
        response.raise_for_status()
        observations.append(decrypt_observation(response.content, private_key_path))

    return observations
