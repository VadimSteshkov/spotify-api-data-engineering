import os
import json
from typing import Any, Dict, List, Optional, Union

try:
    from confluent_kafka import Producer
    _KAFKA_AVAILABLE = True
except Exception:
    Producer = None  # type: ignore
    _KAFKA_AVAILABLE = False


class KafkaJsonProducer:
    """
    Thin wrapper around confluent_kafka that sends dicts or raw JSON strings.
    Reads env:
      - KAFKA_ENABLED=true/false
      - KAFKA_BOOTSTRAP=localhost:9092
      - KAFKA_LINGER_MS=50 (optional)
      - KAFKA_BATCH_SIZE=16384 (optional)
    """

    def __init__(self) -> None:
        self.enabled = os.getenv("KAFKA_ENABLED", "false").lower() == "true"
        self.bootstrap = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
        linger_ms = int(os.getenv("KAFKA_LINGER_MS", "50"))
        batch_size = int(os.getenv("KAFKA_BATCH_SIZE", "16384"))

        if not self.enabled:
            self._producer = None
            print("[KAFKA] Producer disabled by env.")
            return

        if not _KAFKA_AVAILABLE:
            self._producer = None
            print("[KAFKA] confluent-kafka is not installed. Disable KAFKA or install the package.")
            self.enabled = False
            return

        conf = {
            "bootstrap.servers": self.bootstrap,
            "linger.ms": linger_ms,
            "batch.num.messages": 1000,
            "message.max.bytes": 1048576,
            "queue.buffering.max.kbytes": batch_size,
            "enable.idempotence": True,
            "retries": 3,
        }
        self._producer = Producer(conf)
        print(f"[KAFKA] Producer ready (bootstrap={self.bootstrap})")

    def _dr_cb(self, err, msg) -> None:
        if err is not None:
            print(f"[KAFKA] Delivery failed: {err}")

    def _produce(self, topic: str, value: Union[str, Dict[str, Any]]) -> None:
        if not self.enabled or self._producer is None:
            return
        if isinstance(value, str):
            payload_bytes = value.encode("utf-8")
        else:
            payload_bytes = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._producer.produce(topic, payload_bytes, callback=self._dr_cb)

    def send_str(self, topic: str, json_string: str) -> None:
        """Send already-serialized JSON string."""
        self._produce(topic, json_string)

    def send_json(self, topic: str, payload: Dict[str, Any]) -> None:
        """Send a dict that will be json.dumps-ed."""
        self._produce(topic, payload)

    def send_many_json(self, topic: str, payloads: List[Dict[str, Any]]) -> None:
        for p in payloads:
            self._produce(topic, p)

    def flush(self, timeout: Optional[float] = 10.0) -> None:
        if self._producer is not None:
            self._producer.flush(timeout)

