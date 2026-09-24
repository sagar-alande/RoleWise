"""SQS consumer. Run with: python -m rolewise.worker.main"""

import json
import logging
import signal

from rolewise.aws import sqs
from rolewise.config import get_settings
from rolewise.worker.tasks import dispatch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rolewise.worker")
_running = True


def _stop(*_):
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    queue_url = get_settings().sqs_queue_url
    log.info("worker started")
    while _running:
        resp = sqs().receive_message(QueueUrl=queue_url, MaxNumberOfMessages=5, WaitTimeSeconds=20,
                                     VisibilityTimeout=300)
        for msg in resp.get("Messages", []):
            try:
                dispatch(json.loads(msg["Body"]))
                sqs().delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            except Exception:  # noqa: BLE001
                # Leave the message. SQS retries it and moves it to the dead-letter queue after max receives.
                log.warning("message left for retry")
    log.info("worker stopped")


if __name__ == "__main__":
    main()
