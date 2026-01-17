#!/bin/bash
# This script builds the frontend application for staging and deploys it to the AWS S3 staging bucket.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Building the frontend application for STAGING..."
cd frontend
npm run build:staging
cd ..

echo "Build complete. Deploying to AWS S3 (staging.utsulog.in)..."
# Assuming same credentials work
aws s3 sync frontend/dist s3://staging.utsulog.in --delete

echo "Invalidating CloudFront cache..."
# Dynamically find the distribution ID for staging.utsulog.in
DIST_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Aliases.Items!=null] | [?contains(Aliases.Items, 'staging.utsulog.in')].Id" --output text)

if [ -n "$DIST_ID" ] && [ "$DIST_ID" != "None" ]; then
  echo "Found Distribution ID: $DIST_ID"
  aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" --no-cli-pager
else
  echo "Distribution for staging.utsulog.in not found. Skipping invalidation."
  echo "Please create the CloudFront distribution manually or via script if it doesn't exist."
fi

echo "Staging Deployment successful!"
