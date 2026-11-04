import json
import logging
import os
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from observation_builder import build_observation_BRMedida, build_observation_international
from validator import ValidationError, validate_payload


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("observation-processor")


def run() -> None:
    host = os.getenv("MQTT_HOST", "mosquitto")
    port = int(os.getenv("MQTT_PORT", "1883"))
    topic = os.getenv("MQTT_TOPIC", "cgm/measurements")
    output_path = Path(os.getenv("OUTPUT_PATH", "/app/output/observations.jsonl"))
    timezone_name = os.getenv("DATASET_TIMEZONE", "Asia/Shanghai")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def on_connect(
        client: mqtt.Client,
        _userdata: object,
        _flags: dict[str, object],
        reason_code: mqtt.ReasonCode,
        _properties: Any = None,
    ) -> None:
        if reason_code.is_failure:
            logger.error("MQTT connection rejected: %s", reason_code)
            return
        result, _message_id = client.subscribe(topic, qos=0)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error("Failed to subscribe to topic=%s: MQTT rc=%s", topic, result)
            return
        logger.info("Subscribed to topic=%s broker=%s:%d", topic, host, port)

    def on_message(
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            measurement = validate_payload(message.payload, timezone_name)
        except ValidationError as error:
            logger.warning("Rejected message topic=%s: %s", message.topic, error)
            return

        observation = build_observation_international(measurement)
        try:
            with output_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(observation, ensure_ascii=False, allow_nan=False))
                output.write("\n")
        except OSError as error:
            logger.error(
                "Failed to persist Observation id=%s to %s: %s",
                observation["id"],
                output_path,
                error,
            )
            return
        else:
            logger.info(
                "Wrote Observation to JSONL id=%s patient=%s time=%s",
                observation["id"],
                measurement["patient"],
                measurement["time"],
            )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id="observation-processor"
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=60)
    logger.info("Connecting to MQTT broker at %s:%d", host, port)
    client.loop_forever()


if __name__ == "__main__":
    try:
        run()
    except (OSError, ValueError) as error:
        logger.error("%s", error)
        raise SystemExit(1) from error
