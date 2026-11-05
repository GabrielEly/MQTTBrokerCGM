import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import psycopg
import requests
from cryptography.exceptions import InvalidTag
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from storage import ensure_schema, get_patient_observations, store_observation


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("observation-storage")

database_connection = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "observations"),
    "user": os.getenv("POSTGRES_USER", "observations"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}
ipfs_api_url = os.getenv("IPFS_API_URL", "http://ipfs-node:5001")
public_key_path = Path(
    os.getenv(
        "ENCRYPTION_PUBLIC_KEY_PATH",
        "/run/secrets/observations-public.pem",
    )
)
private_key_path = Path(
    os.getenv(
        "ENCRYPTION_PRIVATE_KEY_PATH",
        "/run/secrets/observations-private.pem",
    )
)


class PatientReference(BaseModel):
    reference: str = Field(min_length=1)

    class Config:
        extra = "allow"


class ObservationRequest(BaseModel):
    resourceType: Literal["Observation"]
    id: str = Field(min_length=1)
    subject: PatientReference
    effectiveDateTime: str = Field(min_length=1)

    class Config:
        extra = "allow"


class StoredObservation(BaseModel):
    observation_id: str
    cid: str


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema(database_connection)
    yield


app = FastAPI(
    title="Observation Storage API",
    description="Receives, encrypts, and stores FHIR Observations in IPFS.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/observations", response_model=StoredObservation)
def receive_observation(observation: ObservationRequest) -> StoredObservation:
    try:
        cid = store_observation(
            observation.dict(),
            database_connection,
            ipfs_api_url,
            public_key_path,
        )
    except (OSError, ValueError) as error:
        logger.error(
            "Could not encrypt or store Observation id=%s: %s",
            observation.id,
            error,
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    except requests.RequestException as error:
        logger.error(
            "IPFS request failed for Observation id=%s: %s",
            observation.id,
            error,
        )
        raise HTTPException(status_code=502, detail="IPFS storage failed") from error
    except psycopg.Error as error:
        logger.error(
            "PostgreSQL operation failed for Observation id=%s: %s",
            observation.id,
            error,
        )
        raise HTTPException(
            status_code=503,
            detail="Reference database unavailable",
        ) from error

    return StoredObservation(observation_id=observation.id, cid=cid)


@app.get("/observations")
def read_patient_observations(
    patient_id: str = Query(min_length=1),
) -> list[dict[str, Any]]:
    try:
        return get_patient_observations(
            patient_id,
            database_connection,
            ipfs_api_url,
            private_key_path,
        )
    except requests.RequestException as error:
        logger.error(
            "IPFS request failed while retrieving observations for patient=%s: %s",
            patient_id,
            error,
        )
        raise HTTPException(
            status_code=502,
            detail="IPFS retrieval failed",
        ) from error
    except psycopg.Error as error:
        logger.error(
            "PostgreSQL operation failed while retrieving observations for patient=%s: %s",
            patient_id,
            error,
        )
        raise HTTPException(
            status_code=503,
            detail="Reference database unavailable",
        ) from error
    except (OSError, ValueError, KeyError, TypeError, InvalidTag) as error:
        logger.error(
            "Could not decrypt observations for patient=%s: %s",
            patient_id,
            error,
        )
        raise HTTPException(
            status_code=502,
            detail="Stored observation could not be decrypted",
        ) from error
