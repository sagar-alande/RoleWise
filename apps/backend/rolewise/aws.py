"""AWS clients and the task queue."""

from __future__ import annotations

import json
import logging
import uuid
from functools import lru_cache

import boto3

from rolewise.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def s3():
    s = get_settings()
    return boto3.client("s3", region_name=s.aws_region, endpoint_url=s.aws_endpoint_url)


@lru_cache
def s3_presigner():
    """Presigned URLs must use an endpoint the browser can reach."""
    s = get_settings()
    return boto3.client("s3", region_name=s.aws_region, endpoint_url=s.s3_public_endpoint_url or s.aws_endpoint_url)


@lru_cache
def sqs():
    s = get_settings()
    return boto3.client("sqs", region_name=s.aws_region, endpoint_url=s.aws_endpoint_url)


def enqueue(task: str, run_id: uuid.UUID, payload: dict) -> None:
    """Send a task to the worker. Without a queue URL (tests), the task runs inline."""
    body = {"task": task, "run_id": str(run_id), "payload": payload}
    queue_url = get_settings().sqs_queue_url
    if not queue_url:
        from rolewise.worker.tasks import dispatch

        log.info("No SQS queue configured, running %s inline", task)
        dispatch(body)
        return
    sqs().send_message(QueueUrl=queue_url, MessageBody=json.dumps(body))
