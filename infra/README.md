# RoleWise infrastructure (AWS CDK)

One stack per environment: `RoleWise-dev`, `RoleWise-staging`, `RoleWise-prod`.

| Resource | Service |
| --- | --- |
| web, api | Amazon ECS Express Mode (`AWS::ECS::ExpressGatewayService`) |
| worker | ECS Fargate service, scales on SQS queue depth |
| Database | RDS PostgreSQL 16 (pgvector enabled by the first migration) |
| Files | S3, KMS encrypted, private |
| Tasks | SQS with dead-letter queue |
| Auth | Cognito user pool + web client |
| AI | Bedrock, called by the worker through a VPC endpoint |

## First deploy (once per environment)

Express Mode needs an image to exist, so the first deploy creates everything except the services.

```
cd infra && npm ci
npx cdk bootstrap                                     # once per account/region
npx cdk deploy RoleWise-dev -c env=dev -c deployServices=false
```

Then build and push the first images to the two ECR repositories in the stack outputs, and run:

```
npx cdk deploy RoleWise-dev -c env=dev -c imageTag=<git sha>
```

After that, the GitHub `Deploy` workflow handles everything: build, push, deploy, migrate, smoke test.

## Also set up

1. Enable model access in the Bedrock console for the Claude and Titan Embeddings models in your region.
2. Create a GitHub OIDC deploy role and store its ARN as the `AWS_DEPLOY_ROLE_ARN` secret in each
   GitHub environment. Add required reviewers to the `staging` and `prod` environments.
3. Set an AWS Budgets alert for the account.
4. For a custom domain, add it to the Express Mode services and point Route 53 at the managed load balancer.

## Notes

- The web and api services run in public subnets behind the Express Mode load balancer, with a
  security group that is the only path into the database. Move them to private subnets once you
  confirm the load balancer placement you want for your account.
- The Bedrock IAM policy allows all foundation models. Tighten it to the model ARNs you enable.
- Express Mode does not scale to zero. Dev keeps one task per service. The worker scales to zero in dev.
