# ADR 0001: Deploy on Amazon ECS Express Mode instead of AWS App Runner

Status: accepted (2026-09-23)

## Context

The original plan used AWS App Runner. App Runner stopped accepting new customers on April 30, 2026 and
AWS recommends ECS Express Mode as the replacement.

## Decision

Deploy `web` and `api` as ECS Express Mode services (`AWS::ECS::ExpressGatewayService`). Express Mode
provisions the Fargate service, a shared Application Load Balancer, HTTPS, security groups and auto scaling.
The `worker` has no HTTP endpoint, so it runs as a standard ECS Fargate service that scales on SQS depth.

## Consequences

- CI must build and push images to ECR. Express Mode does not build from source.
- No scale to zero. Keep dev tasks small to control cost.
- We keep full access to standard ECS features if we outgrow Express Mode.
