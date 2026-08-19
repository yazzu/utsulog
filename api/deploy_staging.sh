#!/bin/bash
set -e

# 設定
# PROJECT_ROOTはスクリプトのあるディレクトリの親ディレクトリ
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

AWS_REGION="ap-northeast-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="utsulog-api"
IMAGE_TAG="staging"
IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}"
LAMBDA_FUNCTION_NAME="utsulog-api-staging"
ENV_FILE=".env.staging"

# .envファイルからJSON形式の環境変数ペイロードを組み立てる関数。
# AWS CLIのshorthand構文(Variables={KEY=VALUE,...})は値自体にカンマを含む
# CORS_ORIGINS(複数オリジンをカンマ区切り)のようなケースをパースできないため、
# JSON形式で渡す。
load_env_vars_json() {
    local env_file=$1
    python3 - "$env_file" <<'PYEOF'
import json
import sys

env_file = sys.argv[1]
skip_keys = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"}
variables = {}
with open(env_file) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key in skip_keys or not value:
            continue
        variables[key] = value

print(json.dumps({"Variables": variables}))
PYEOF
}

echo "Loading environment variables from ${ENV_FILE}..."
ENV_JSON=$(load_env_vars_json "${ENV_FILE}")

echo "Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo "Building Docker image for Staging..."
# --provenance=false --sbom=false: Lambdaはbuildxが既定で付与するOCIのprovenance/SBOM
# attestationを含むマニフェスト形式を受け付けないため、単純なDocker V2形式でビルドする。
docker build --provenance=false --sbom=false --platform linux/amd64 -t ${ECR_REPO_NAME}:${IMAGE_TAG} -f api/Dockerfile.lambda api

echo "Tagging image..."
docker tag ${ECR_REPO_NAME}:${IMAGE_TAG} ${IMAGE_URI}

echo "Pushing image to ECR..."
docker push ${IMAGE_URI}

echo "Deploying to Staging Lambda function: ${LAMBDA_FUNCTION_NAME}..."

# Lambda関数が存在するか確認
if aws lambda get-function --function-name ${LAMBDA_FUNCTION_NAME} >/dev/null 2>&1; then
    echo "Updating existing Staging Lambda function code..."
    aws lambda update-function-code --function-name ${LAMBDA_FUNCTION_NAME} --image-uri ${IMAGE_URI}
    
    echo "Waiting for update to complete..."
    aws lambda wait function-updated --function-name ${LAMBDA_FUNCTION_NAME}

    echo "Updating environment variables..."
    aws lambda update-function-configuration \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --environment "${ENV_JSON}"

else
    echo "Creating new Staging Lambda function..."
    # 既存のロールを使用
    ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/utsulog-api-lambda-role"
    
    # ロールチェック（簡易）
    if ! aws iam get-role --role-name utsulog-api-lambda-role >/dev/null 2>&1; then
        echo "Role not found. Please ensure 'utsulog-api-lambda-role' exists."
        exit 1
    fi

    aws lambda create-function \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --package-type Image \
        --code ImageUri=${IMAGE_URI} \
        --role ${ROLE_ARN} \
        --timeout 30 \
        --memory-size 512 \
        --environment "${ENV_JSON}"

    echo "Creating Function URL..."
    aws lambda create-function-url-config \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --auth-type NONE
        
    echo "Adding permission for public access..."
    aws lambda add-permission \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --statement-id FunctionURLAllowPublicAccess \
        --action lambda:InvokeFunctionUrl \
        --principal "*" \
        --function-url-auth-type NONE
fi

echo "Staging Deployment completed!"
echo "Staging Function URL:"
aws lambda get-function-url-config --function-name ${LAMBDA_FUNCTION_NAME} --query FunctionUrl --output text
