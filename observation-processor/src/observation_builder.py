import hashlib
import json
from typing import Any


MMOL_L_TO_MG_DL = 18.0182


def build_observation_BRMedida(measurement: dict[str, Any]) -> dict[str, Any]:
    value = measurement["glucose"]
    unit = measurement["unit"]
    if unit == "mmol/L":
        value = value * MMOL_L_TO_MG_DL
        unit = "mg/dL"

    identity = json.dumps(
        [
            measurement["patient"],
            measurement["device"],
            measurement["time"],
            measurement["glucose"],
            measurement["unit"],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    resource_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:64]
    return {
        "resourceType": "Observation",
        "id": resource_id,
        "meta": {
            "profile": [
                "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRMedidaObservada"
            ]
        },
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "99504-3",
                    "display": "Glucose [Mass/volume] in Interstitial fluid",
                }
            ],
            "text": "Glicose intersticial",
        },
        "valueQuantity": {
            "value": value,
            "unit": unit,
            "system": "https://www.hl7.org/fhir/valueset-ucum-common.html",
            "code": unit,
        },
        "bodySite": {
            "coding": [
                {
                    "system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRLocalAfericao",
                    "code": "1",
                    "display": "Braco direito",
                }
            ]
        },
        "method": {
            "coding": [
                {
                    "system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRPosicaoIndividuo",
                    "code": "2",
                    "display": "Sentado",
                }
            ]
        },
        "effectiveDateTime": measurement["time"],
        "subject": {"reference": f"Patient/{measurement['patient']}"},
        "device": {"reference": f"Device/{measurement['device']}"},
    }

def build_observation_international(measurement: dict[str, Any]) -> dict[str, Any]:
    value = measurement["glucose"]
    unit = measurement["unit"]
    if unit == "mmol/L":
        value = value * MMOL_L_TO_MG_DL
        unit = "mg/dL"

    identity = json.dumps(
        [
            measurement["patient"],
            measurement["device"],
            measurement["time"],
            measurement["glucose"],
            measurement["unit"],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    resource_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:64]
    return {
        "resourceType": "Observation",
        "id": resource_id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category", 
                "code": "laboratory", 
                "display": "Laboratory"
            }]
        }],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "99504-3",
                    "display": "Glucose [Mass/volume] in Interstitial fluid",
                }
            ],
            "text": "Glicose intersticial",
        },
        "subject": {"reference": f"urn:uuid:{measurement['patient']}"},
        "effectiveDateTime": measurement["time"],
        "valueQuantity": {
            "value": value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
            "code": unit,
        },
        "device": {"reference": f"urn:uuid:{measurement['device']}"}
    }
