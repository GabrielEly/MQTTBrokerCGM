import csv
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import paho.mqtt.client as mqtt


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("cgm-simulator")


@dataclass(frozen=True)
class Measurement:
    patient: str
    time: str
    glucose: Union[int, float]
    unit: str


def _parse_time(value: str, time_format: str, timezone: ZoneInfo) -> datetime:
    if time_format:
        parsed = datetime.strptime(value.strip(), time_format)
    else:
        normalized = value.strip()
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed


def _resolve_column(
    headers: list[str], configured_column: str, aliases: tuple[str, ...] = ()
) -> Optional[str]:
    candidates = (configured_column, *aliases)
    for candidate in candidates:
        normalized_candidate = candidate.strip().casefold()
        for header in headers:
            if header.strip().casefold() == normalized_candidate:
                return header
    return None


def load_measurements() -> list[Measurement]:
    data_path = Path(os.getenv("DATASET_PATH", "/app/data"))
    patient_column = os.getenv("DATASET_PATIENT_COLUMN", "").strip()
    patient_from_filename = os.getenv("DATASET_PATIENT_FROM_FILENAME", "false").lower() == "true"
    time_column = os.getenv("DATASET_TIME_COLUMN", "").strip()
    glucose_column = os.getenv("DATASET_GLUCOSE_COLUMN", "").strip()
    unit = os.getenv("DATASET_GLUCOSE_UNIT", "").strip()
    time_format = os.getenv("DATASET_TIME_FORMAT", "").strip()
    selected_patient = os.getenv("PATIENT_ID", "").strip()
    timezone_name = os.getenv("DATASET_TIMEZONE", "Asia/Shanghai")

    missing = [
        name
        for name, value in (
            ("DATASET_TIME_COLUMN", time_column),
            ("DATASET_GLUCOSE_COLUMN", glucose_column),
            ("DATASET_GLUCOSE_UNIT", unit),
        )
        if not value
    ]
    if not patient_column and not patient_from_filename:
        missing.append("DATASET_PATIENT_COLUMN or DATASET_PATIENT_FROM_FILENAME=true")
    if missing:
        raise ValueError("Configure the dataset mapping: " + ", ".join(missing))
    if unit not in {"mg/dL", "mmol/L"}:
        raise ValueError("DATASET_GLUCOSE_UNIT must explicitly be mg/dL or mmol/L")
    if not data_path.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {data_path}")
    files = sorted(data_path.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found under {data_path}")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown DATASET_TIMEZONE: {timezone_name}") from error

    measurements: list[Measurement] = []
    for file_path in files:
        with file_path.open("r", encoding="utf-8-sig", newline="") as source:
            sample = source.read(8192)
            source.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(source, dialect=dialect)
            headers = reader.fieldnames or []
            time_header = _resolve_column(headers, time_column)
            glucose_aliases = (
                ("CGM", "CGM (mg / dl)")
                if glucose_column.casefold() in {"cgm", "cgm (mg / dl)"}
                else ()
            )
            glucose_header = _resolve_column(
                headers, glucose_column, glucose_aliases
            )
            if time_header is None and glucose_header is None:
                logger.info(
                    "Skipping non-measurement CSV %s: configured time and glucose "
                    "columns are absent",
                    file_path,
                )
                continue
            patient_header = (
                _resolve_column(headers, patient_column) if patient_column else None
            )
            resolved_columns = [
                (time_column, time_header),
                (glucose_column, glucose_header),
            ]
            if patient_column:
                resolved_columns.append((patient_column, patient_header))
            missing_columns = [
                column
                for column, resolved in resolved_columns
                if resolved is None
            ]
            if missing_columns:
                raise ValueError(
                    f"{file_path}: configured column(s) not found: "
                    f"{', '.join(missing_columns)}; available columns: {headers}"
                )

            if patient_column:
                filename_patient = ""
            elif patient_from_filename:
                filename_parts = file_path.stem.split("_")
                if len(filename_parts) < 3 or not filename_parts[0]:
                    raise ValueError(
                        f"{file_path}: expected filename format "
                        "<patient>_<record>_<date>.csv to derive patient ID"
                    )
                filename_patient = filename_parts[0]
            else:
                filename_patient = ""

            for row_number, row in enumerate(reader, start=2):
                if not str(row.get(time_header) or "").strip() and not str(
                    row.get(glucose_header) or ""
                ).strip():
                    continue
                try:
                    patient_value = (
                        row[patient_header]
                        if patient_header
                        else filename_patient
                    )
                    patient = patient_value.strip() if patient_value else ""
                    timestamp = _parse_time(
                        str(row[time_header]), time_format, timezone
                    )
                    glucose = float(str(row[glucose_header]).strip())
                    if not patient or not math.isfinite(glucose) or glucose <= 0:
                        raise ValueError("empty patient or invalid glucose value")
                    if selected_patient and patient != selected_patient:
                        continue
                    original_glucose: Union[int, float] = (
                        int(glucose) if glucose.is_integer() else glucose
                    )
                    measurements.append(
                        Measurement(
                            patient=patient,
                            time=timestamp.isoformat(),
                            glucose=original_glucose,
                            unit=unit,
                        )
                    )
                except (KeyError, TypeError, ValueError, OverflowError) as error:
                    logger.warning(
                        "Skipping unparseable row %s:%d (%s)",
                        file_path,
                        row_number,
                        error,
                    )

    measurements.sort(
        key=lambda measurement: datetime.fromisoformat(measurement.time)
    )
    if not measurements:
        raise ValueError("No valid measurements found for the configured dataset mapping")
    return measurements


def _connect(client: mqtt.Client, host: str, port: int) -> None:
    connected = False

    def on_connect(
        _client: mqtt.Client,
        _userdata: object,
        _flags: dict[str, object],
        reason_code: mqtt.ReasonCode,
        _properties: Any = None,
    ) -> None:
        nonlocal connected
        if reason_code.is_failure:
            logger.error("MQTT connection rejected: %s", reason_code)
        else:
            connected = True

    client.on_connect = on_connect
    client.connect(host, port, keepalive=60)
    client.loop_start()
    deadline = time.monotonic() + 15
    while not connected and time.monotonic() < deadline:
        time.sleep(0.1)
    if not connected:
        client.loop_stop()
        raise TimeoutError(f"Could not connect to MQTT broker at {host}:{port}")


def run() -> None:
    host = os.getenv("MQTT_HOST", "mosquitto")
    port = int(os.getenv("MQTT_PORT", "1883"))
    topic = os.getenv("MQTT_TOPIC", "cgm/measurements")
    device = os.getenv("CGM_DEVICE_ID", "cgm-sim-01")
    interval = float(os.getenv("SIM_INTERVAL_SECONDS", "1"))
    repeat = os.getenv("SIM_REPEAT", "false").lower() == "true"
    start_delay = float(os.getenv("SIM_START_DELAY_SECONDS", "2"))
    if (
        not math.isfinite(interval)
        or not math.isfinite(start_delay)
        or interval < 0
        or start_delay < 0
    ):
        raise ValueError(
            "SIM_INTERVAL_SECONDS and SIM_START_DELAY_SECONDS must be finite "
            "and cannot be negative"
        )

    measurements = load_measurements()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="cgm-simulator")
    _connect(client, host, port)
    try:
        if start_delay:
            time.sleep(start_delay)
        while True:
            for measurement in measurements:
                payload = {
                    "patient": measurement.patient,
                    "device": device,
                    "time": measurement.time,
                    "glucose": measurement.glucose,
                    "unit": measurement.unit,
                }
                info = client.publish(
                    topic, json.dumps(payload, allow_nan=False), qos=0
                )
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    logger.error("Failed to publish measurement: MQTT rc=%s", info.rc)
                    continue
                info.wait_for_publish(timeout=5)
                logger.info(
                    "Published patient=%s time=%s glucose=%s %s topic=%s",
                    measurement.patient,
                    measurement.time,
                    measurement.glucose,
                    measurement.unit,
                    topic,
                )
                if interval:
                    time.sleep(interval)
            if not repeat:
                break
    finally:
        client.disconnect()
        client.loop_stop()
    logger.info("Dataset playback completed")


if __name__ == "__main__":
    try:
        run()
    except (FileNotFoundError, ValueError, TimeoutError, OSError) as error:
        logger.error("%s", error)
        raise SystemExit(1) from error
