#!/bin/bash
# Runs inside LocalStack when it is ready. Creates the local bucket and queue.
awslocal s3 mb s3://rolewise-documents
awslocal sqs create-queue --queue-name rolewise-tasks

# The browser PUTs resume files straight to S3 using a presigned URL (see resume_upload_url in
# rolewise/api/routers/profile.py), a cross-origin request from localhost:3000 to localhost:4566.
# Without CORS, the browser blocks it before the app ever sees a response.
awslocal s3api put-bucket-cors --bucket rolewise-documents --cors-configuration '{
  "CORSRules": [{
    "AllowedOrigins": ["*"],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"]
  }]
}'
