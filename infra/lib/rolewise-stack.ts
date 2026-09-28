import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sqs from "aws-cdk-lib/aws-sqs";

export interface RoleWiseStackProps extends cdk.StackProps {
  envName: "dev" | "staging" | "prod";
  /** Image tag (git SHA) to deploy. On the very first deploy, set deployServices=false until images exist. */
  imageTag: string;
  deployServices: boolean;
  /** Web app origin(s) allowed as Cognito Hosted UI OAuth callback/logout targets, e.g.
   * ["https://app.rolewise.example", "http://localhost:3000"] (the second only while testing Google
   * sign-in against a deployed pool from local dev). Only used when googleClientId is set. */
  webOrigins?: string[];
  /** Google OAuth client ID (from Google Cloud Console's OAuth consent screen setup) - not secret.
   * Leave unset to deploy without Google Sign-In (the pool falls back to its plain SRP client, as
   * before this feature existed). */
  googleClientId?: string;
  /** Name of a Secrets Manager secret, created out-of-band, holding the Google OAuth client secret:
   *   aws secretsmanager create-secret --name rolewise/google-oauth-client-secret --secret-string '<secret>'
   * Read by CloudFormation at deploy time via SecretValue.secretsManager - never appears in this
   * file, CDK context, CLI history, or the synthesized template. */
  googleClientSecretName?: string;
}

/**
 * RoleWise on AWS.
 *  - web and api: Amazon ECS Express Mode (App Runner is closed to new customers)
 *  - worker: standard ECS Fargate service scaled on SQS queue depth
 *  - RDS PostgreSQL 16 (pgvector), S3, SQS + DLQ, Cognito, Bedrock access through IAM
 */
export class RoleWiseStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: RoleWiseStackProps) {
    super(scope, id, props);
    const isProd = props.envName === "prod";
    const name = (s: string) => `rolewise-${props.envName}-${s}`;

    // ---------------------------------------------------------------- network
    // Dev/staging: no NAT gateway, no interface endpoints (~$118/mo) - the worker runs in a public
    // subnet instead, same tradeoff the web/api Express services already make (see infra/README.md).
    // Prod: worker stays in a private-with-egress subnet behind NAT, reaching AWS services over
    // interface endpoints instead of the public internet.
    const vpc = new ec2.Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: isProd ? 2 : 0,
      subnetConfiguration: [
        { name: "public", subnetType: ec2.SubnetType.PUBLIC },
        ...(isProd ? [{ name: "app", subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS }] : []),
        { name: "data", subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      ],
    });
    // Always free (no hourly charge) - keep S3 traffic off the public internet regardless of env.
    vpc.addGatewayEndpoint("S3Endpoint", { service: ec2.GatewayVpcEndpointAwsService.S3 });
    if (isProd) {
      for (const [id, svc] of [
        ["Ecr", ec2.InterfaceVpcEndpointAwsService.ECR],
        ["EcrDocker", ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER],
        ["Sqs", ec2.InterfaceVpcEndpointAwsService.SQS],
        ["Secrets", ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER],
        ["Logs", ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS],
        ["Bedrock", ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME],
      ] as const) {
        vpc.addInterfaceEndpoint(`${id}Endpoint`, { service: svc, subnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS } });
      }
    }

    const appSg = new ec2.SecurityGroup(this, "AppSg", { vpc, description: "RoleWise application tasks" });
    const dbSg = new ec2.SecurityGroup(this, "DbSg", { vpc, description: "RoleWise database" });
    dbSg.addIngressRule(appSg, ec2.Port.tcp(5432), "App tasks to Postgres");

    // ---------------------------------------------------------------- data
    const db = new rds.DatabaseInstance(this, "Db", {
      engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_16 }),
      instanceType: isProd
        ? ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MEDIUM)
        : ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [dbSg],
      databaseName: "rolewise",
      credentials: rds.Credentials.fromGeneratedSecret("rolewise"),
      storageEncrypted: true,
      multiAz: isProd,
      allocatedStorage: 20,
      backupRetention: cdk.Duration.days(isProd ? 14 : 1),
      deletionProtection: isProd,
      removalPolicy: isProd ? cdk.RemovalPolicy.SNAPSHOT : cdk.RemovalPolicy.DESTROY,
    });

    const bucket = new s3.Bucket(this, "Documents", {
      bucketName: `${name("documents")}-${this.account}`,
      encryption: s3.BucketEncryption.KMS_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: isProd,
      cors: [{ allowedMethods: [s3.HttpMethods.PUT], allowedOrigins: ["*"], allowedHeaders: ["*"] }],
      removalPolicy: isProd ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: !isProd,
    });

    const dlq = new sqs.Queue(this, "TasksDlq", {
      queueName: name("tasks-dlq"),
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
    });
    const queue = new sqs.Queue(this, "Tasks", {
      queueName: name("tasks"),
      visibilityTimeout: cdk.Duration.minutes(6),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      deadLetterQueue: { queue: dlq, maxReceiveCount: 3 },
    });

    // ---------------------------------------------------------------- auth
    const userPool = new cognito.UserPool(this, "Users", {
      userPoolName: name("users"),
      selfSignUpEnabled: true,
      signInAliases: { email: true },
      autoVerify: { email: true },
      passwordPolicy: { minLength: 10, requireSymbols: false },
      removalPolicy: isProd ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
    });

    // Google Sign-In: federates Google into this same User Pool, so the API's existing JWT
    // verification (auth.py - issuer + client_id pinned to this pool/client) needs no changes at
    // all - a Google-authenticated user just gets a Cognito sub like "Google_<id>", handled by the
    // same _get_or_create() as any other sub. Only active when googleClientId is supplied, so a
    // deploy without it behaves exactly as before this feature existed.
    const googleEnabled = !!props.googleClientId;
    let userPoolClient: cognito.UserPoolClient;
    let hostedUiDomain: cognito.UserPoolDomain | undefined;

    if (googleEnabled) {
      const googleIdp = new cognito.UserPoolIdentityProviderGoogle(this, "Google", {
        userPool,
        clientId: props.googleClientId!,
        // Never a plain string here - CloudFormation resolves this from Secrets Manager at deploy
        // time, so the secret itself never appears in this file, CDK context, or CLI history.
        clientSecretValue: cdk.SecretValue.secretsManager(
          props.googleClientSecretName ?? "rolewise/google-oauth-client-secret",
        ),
        scopes: ["openid", "email", "profile"],
        attributeMapping: { email: cognito.ProviderAttribute.GOOGLE_EMAIL },
      });
      hostedUiDomain = userPool.addDomain("HostedUiDomain", {
        cognitoDomain: { domainPrefix: name("auth").replace(/[^a-z0-9-]/g, "") },
      });
      const webOrigins = props.webOrigins ?? ["http://localhost:3000"];
      userPoolClient = userPool.addClient("WebClient", {
        generateSecret: false, // public SPA client - Authorization Code + PKCE, no secret to protect
        oAuth: {
          flows: { authorizationCodeGrant: true },
          scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
          callbackUrls: webOrigins.map((o) => `${o}/callback`),
          logoutUrls: webOrigins,
        },
        // Google only - the Hosted UI goes straight to "Continue with Google", no separate
        // Cognito-native email/password option, matching what was actually asked for.
        supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.GOOGLE],
      });
      userPoolClient.node.addDependency(googleIdp); // the client references the IdP by name
    } else {
      userPoolClient = userPool.addClient("WebClient", { authFlows: { userSrp: true }, generateSecret: false });
    }

    // ---------------------------------------------------------------- images and roles
    const webRepo = new ecr.Repository(this, "WebRepo", { repositoryName: name("web"), imageScanOnPush: true });
    const backendRepo = new ecr.Repository(this, "BackendRepo", { repositoryName: name("backend"), imageScanOnPush: true });

    const executionRole = new iam.Role(this, "ExecutionRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AmazonECSTaskExecutionRolePolicy")],
    });
    db.secret!.grantRead(executionRole);

    const infrastructureRole = new iam.Role(this, "ExpressInfraRole", {
      assumedBy: new iam.ServicePrincipal("ecs.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"),
      ],
    });

    const apiTaskRole = new iam.Role(this, "ApiTaskRole", { assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com") });
    bucket.grantReadWrite(apiTaskRole, "resumes/*");
    queue.grantSendMessages(apiTaskRole);

    const workerTaskRole = new iam.Role(this, "WorkerTaskRole", { assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com") });
    bucket.grantReadWrite(workerTaskRole);
    queue.grantConsumeMessages(workerTaskRole);
    queue.grantSendMessages(workerTaskRole);
    workerTaskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:InvokeModel", "bedrock:Converse"],
        // Tighten to the specific model and inference-profile ARNs you enable.
        resources: ["arn:aws:bedrock:*::foundation-model/*", `arn:aws:bedrock:*:${this.account}:inference-profile/*`],
      }),
    );

    const cluster = new ecs.Cluster(this, "Cluster", { vpc, clusterName: name("cluster"), containerInsightsV2: ecs.ContainerInsights.ENABLED });

    const sharedEnv: Record<string, string> = {
      APP_ENV: props.envName,
      AWS_REGION: this.region,
      S3_BUCKET: bucket.bucketName,
      SQS_QUEUE_URL: queue.queueUrl,
      BEDROCK_ENABLED: "true",
      COGNITO_USER_POOL_ID: userPool.userPoolId,
      COGNITO_APP_CLIENT_ID: userPoolClient.userPoolClientId,
    };
    const dbSecret = { name: "DB_SECRET", valueFrom: db.secret!.secretArn };

    // ---------------------------------------------------------------- worker (always defined so CI can run migrations)
    const workerLogs = new logs.LogGroup(this, "WorkerLogs", { retention: logs.RetentionDays.ONE_MONTH });
    const workerTaskDef = new ecs.FargateTaskDefinition(this, "WorkerTaskDef", {
      cpu: 512,
      memoryLimitMiB: 1024,
      executionRole,
      taskRole: workerTaskRole,
      runtimePlatform: { cpuArchitecture: ecs.CpuArchitecture.X86_64 },
    });
    workerTaskDef.addContainer("worker", {
      image: ecs.ContainerImage.fromEcrRepository(backendRepo, props.imageTag),
      command: ["python", "-m", "rolewise.worker.main"],
      environment: sharedEnv,
      secrets: { DB_SECRET: ecs.Secret.fromSecretsManager(db.secret!) },
      logging: ecs.LogDrivers.awsLogs({ logGroup: workerLogs, streamPrefix: "worker" }),
    });

    // Where the worker (and one-off migration tasks) reach the internet: a private subnet behind
    // NAT in prod, or directly in the public subnet in dev/staging (no NAT gateway exists there).
    const egressSubnetType = isProd ? ec2.SubnetType.PRIVATE_WITH_EGRESS : ec2.SubnetType.PUBLIC;
    const egressSubnetIds = vpc.selectSubnets({ subnetType: egressSubnetType }).subnetIds;

    if (props.deployServices) {
      const publicSubnets = vpc.publicSubnets.map((s) => s.subnetId);

      const worker = new ecs.FargateService(this, "Worker", {
        cluster,
        taskDefinition: workerTaskDef,
        desiredCount: isProd ? 1 : 0,
        securityGroups: [appSg],
        vpcSubnets: { subnetType: egressSubnetType },
        assignPublicIp: !isProd,
        minHealthyPercent: 100,
        circuitBreaker: { rollback: true },
      });
      const scaling = worker.autoScaleTaskCount({ minCapacity: isProd ? 1 : 0, maxCapacity: 5 });
      scaling.scaleOnMetric("QueueDepth", {
        metric: queue.metricApproximateNumberOfMessagesVisible({ period: cdk.Duration.minutes(1) }),
        scalingSteps: [
          { upper: 0, change: isProd ? 0 : -1 },
          { lower: 1, change: +1 },
          { lower: 50, change: +2 },
        ],
      });

      // API on ECS Express Mode. Express Mode creates the ALB, HTTPS listener, target group and scaling.
      const api = new ecs.CfnExpressGatewayService(this, "Api", {
        serviceName: name("api"),
        cluster: cluster.clusterName,
        infrastructureRoleArn: infrastructureRole.roleArn,
        executionRoleArn: executionRole.roleArn,
        taskRoleArn: apiTaskRole.roleArn,
        cpu: "512",
        memory: "1024",
        healthCheckPath: "/health",
        networkConfiguration: { subnets: publicSubnets, securityGroups: [appSg.securityGroupId] },
        primaryContainer: {
          image: backendRepo.repositoryUriForTag(props.imageTag),
          containerPort: 8000,
          environment: Object.entries(sharedEnv).map(([n, v]) => ({ name: n, value: v })),
          secrets: [dbSecret],
        },
        scalingTarget: { minTaskCount: isProd ? 2 : 1, maxTaskCount: isProd ? 10 : 2, autoScalingMetric: "AVERAGE_CPU", autoScalingTargetValue: 60 },
      });

      const web = new ecs.CfnExpressGatewayService(this, "Web", {
        serviceName: name("web"),
        cluster: cluster.clusterName,
        infrastructureRoleArn: infrastructureRole.roleArn,
        executionRoleArn: executionRole.roleArn,
        cpu: "256",
        memory: "512",
        healthCheckPath: "/",
        networkConfiguration: { subnets: publicSubnets, securityGroups: [appSg.securityGroupId] },
        primaryContainer: { image: webRepo.repositoryUriForTag(props.imageTag), containerPort: 3000 },
        scalingTarget: { minTaskCount: isProd ? 2 : 1, maxTaskCount: isProd ? 6 : 2, autoScalingMetric: "AVERAGE_CPU", autoScalingTargetValue: 60 },
      });
      web.node.addDependency(api);

      new cdk.CfnOutput(this, "ApiEndpoint", { value: api.attrEndpoint });
      new cdk.CfnOutput(this, "WebEndpoint", { value: web.attrEndpoint });
    }

    // ---------------------------------------------------------------- outputs used by CI
    new cdk.CfnOutput(this, "ClusterName", { value: cluster.clusterName });
    new cdk.CfnOutput(this, "WorkerTaskDefinition", { value: workerTaskDef.taskDefinitionArn });
    new cdk.CfnOutput(this, "AppSecurityGroup", { value: appSg.securityGroupId });
    // A one-off migration task needs a route to the internet (to reach ECR and the DB's Secrets
    // Manager secret over HTTPS) plus a public IP when it lands in a public subnet - see
    // egressSubnetType above. CI must pass --enable-execute-command network settings matching this.
    new cdk.CfnOutput(this, "MigrationSubnets", { value: egressSubnetIds.join(",") });
    new cdk.CfnOutput(this, "MigrationAssignPublicIp", { value: isProd ? "DISABLED" : "ENABLED" });
    new cdk.CfnOutput(this, "WebRepoUri", { value: webRepo.repositoryUri });
    new cdk.CfnOutput(this, "BackendRepoUri", { value: backendRepo.repositoryUri });
    new cdk.CfnOutput(this, "UserPoolId", { value: userPool.userPoolId });
    new cdk.CfnOutput(this, "UserPoolClientId", { value: userPoolClient.userPoolClientId });
    if (hostedUiDomain) {
      new cdk.CfnOutput(this, "CognitoHostedUiDomain", { value: hostedUiDomain.baseUrl() });
    }
  }
}
