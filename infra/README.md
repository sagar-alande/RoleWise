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

Express Mode needs an image to exist, so the first deploy creates everything except the services. The
web image also needs the API's real URL baked in at build time (see `apps/web/lib/api.ts`), and that
URL doesn't exist until the api service is up - so the very first deploy unavoidably takes two passes.
All commands below run from the repo root unless noted.

**1. Infra only** (VPC, RDS, S3, SQS, Cognito, the two ECR repos - no services yet):

```
cd infra && npm ci
npx cdk bootstrap                                     # once per account/region
npx cdk deploy RoleWise-dev -c env=dev -c deployServices=false
cd ..
```

**2. Build and push both images**, using whatever placeholder API URL you like for this first web
build (pass 4 replaces it with the real one):

```
docker build -f apps/backend/Dockerfile -t <backend-ecr-uri>:<tag> .
docker push <backend-ecr-uri>:<tag>

docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_URL=http://placeholder \
  -t <web-ecr-uri>:<tag> ./apps/web
docker push <web-ecr-uri>:<tag>
```

(`<backend-ecr-uri>` / `<web-ecr-uri>` are the `BackendRepoUri` / `WebRepoUri` stack outputs from step 1.)

**3. Deploy the services** and read back the real endpoints:

```
npx cdk deploy RoleWise-dev -c env=dev -c imageTag=<tag>
```

Note the `ApiEndpoint` and `WebEndpoint` outputs (each is a bare hostname; the web app is served over
HTTPS, so the actual origin is `https://<WebEndpoint>`).

**4. Rebuild the web image with the real API URL**, and redeploy with `webOrigins` set so the API's
CORS allowlist (and, later, Cognito's Hosted UI callback allowlist if Google Sign-In is enabled) covers
the real web origin - `apps/backend/rolewise/api/main.py` allows no cross-origin browser access at all
until this runs:

```
docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://<ApiEndpoint> \
  -t <web-ecr-uri>:<tag> ./apps/web
docker push <web-ecr-uri>:<tag>

cd infra
npx cdk deploy RoleWise-dev -c env=dev -c imageTag=<tag> -c webOrigins=https://<WebEndpoint>
cd ..
```

Every deploy after this one is a single `cdk deploy ... -c imageTag=<new tag>` once both images are
rebuilt and pushed - only the very first deploy needs the placeholder pass, since the API URL and web
origin don't change on their own between deploys.

There is no GitHub Actions workflow yet, so every step above is run by hand.

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
