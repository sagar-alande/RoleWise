#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { RoleWiseStack } from "../lib/rolewise-stack";

const app = new cdk.App();

const envName = (app.node.tryGetContext("env") ?? "dev") as "dev" | "staging" | "prod";
const imageTag = app.node.tryGetContext("imageTag") ?? "latest";
const deployServices = (app.node.tryGetContext("deployServices") ?? "true") !== "false";

new RoleWiseStack(app, `RoleWise-${envName}`, {
  envName,
  imageTag,
  deployServices,
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? "us-east-1" },
});
