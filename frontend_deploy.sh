#!/bin/bash
# フロントエンドをビルドし、S3 + CloudFrontへデプロイする。
# Usage: ./frontend_deploy.sh [staging|prod]  (省略時は staging)
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

ENVIRONMENT="${1:-staging}"

case "$ENVIRONMENT" in
    staging)
        BUCKET="staging.utsulog.in"
        BUILD_CMD="npm run build:staging"
        ;;
    prod)
        BUCKET="utsulog.in"
        BUILD_CMD="npm run build"
        ;;
    *)
        echo "Usage: $0 [staging|prod]"
        exit 1
        ;;
esac

echo "Building the frontend application for ${ENVIRONMENT}..."
(cd frontend && ${BUILD_CMD})

echo "Deploying to AWS S3 (${BUCKET})..."
aws s3 sync frontend/dist "s3://${BUCKET}" --delete

echo "Invalidating CloudFront cache..."
DIST_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Aliases.Items!=null] | [?contains(Aliases.Items, '${BUCKET}')].Id" --output text)

if [ -n "$DIST_ID" ] && [ "$DIST_ID" != "None" ]; then
    echo "Found Distribution ID: $DIST_ID"
    aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" --no-cli-pager
else
    echo "Distribution for ${BUCKET} not found. Skipping invalidation."
    echo "Please create the CloudFront distribution manually or via script if it doesn't exist."
fi

echo "${ENVIRONMENT} Frontend Deployment successful!"
