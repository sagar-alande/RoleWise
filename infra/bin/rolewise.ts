#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { RoleWiseStack } from "../lib/rolewise-stack";

const app = new cdk.App();

const envName = (app.node.tryGetContext("env") ?? "dev") as "dev" | "staging" | "prod";
const imageTag = app.node.tryGetContext("imageTag") ?? "latest";
const deployServices = (app.node.tryGetContext("deployServices") ?? "true") !== "false";

// Google Sign-In (optional): pass with `-c googleClientId=... -c webOrigins=https://app.example,http://localhost:3000`.
// The Google OAuth client SECRET is never passed here - see googleClientSecretName in rolewise-stack.ts.
const webOriginsCtx = app.node.tryGetContext("webOrigins") as string | undefined;
const googleClientId = app.node.tryGetContext("googleClientId") as string | undefined;
const googleClientSecretName = app.node.tryGetContext("googleClientSecretName") as string | undefined;

new RoleWiseStack(app, `RoleWise-${envName}`, {
  envName,
  imageTag,
  deployServices,
  webOrigins: webOriginsCtx?.split(","),
  googleClientId,
  googleClientSecretName,
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? "us-east-1" },
});
