#!/bin/bash
set -e

# 設定
# PROJECT_ROOTはスクリプトのあるディレクトリの親ディレクトリ
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

AWS_REGION="ap-northeast-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="utsulog-api"
IMAGE_TAG="latest"
IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}"
LAMBDA_FUNCTION_NAME="utsulog-api-lambda"
ENV_FILE=".env.prod"

# .envファイルから環境変数を読み込む関数
load_env_vars() {
    local env_file=$1
    local env_vars=""
    while IFS='=' read -r key value || [ -n "$key" ]; do
        if [[ $key =~ ^# ]] || [[ -z $key ]]; then
            continue
        fi
        
        # Lambdaの予約済み環境変数をスキップ
        if [[ "$key" == "AWS_ACCESS_KEY_ID" ]] || [[ "$key" == "AWS_SECRET_ACCESS_KEY" ]] || [[ "$key" == "AWS_DEFAULT_REGION" ]]; then
            continue
        fi

        if [ -n "$value" ]; then
            env_vars="${env_vars}${key}=${value},"
        fi
    done < "$env_file"
    echo "${env_vars%,}"
}

echo "Loading environment variables from ${ENV_FILE}..."
ENV_VARS=$(load_env_vars "${ENV_FILE}")

echo "Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo "Building Docker image for Production..."
docker build --platform linux/amd64 -t ${ECR_REPO_NAME}:${IMAGE_TAG} -f api/Dockerfile.lambda api

echo "Tagging image..."
docker tag ${ECR_REPO_NAME}:${IMAGE_TAG} ${IMAGE_URI}

echo "Pushing image to ECR..."
docker push ${IMAGE_URI}

echo "Deploying to Production Lambda function: ${LAMBDA_FUNCTION_NAME}..."

# Lambda関数が存在するか確認
if aws lambda get-function --function-name ${LAMBDA_FUNCTION_NAME} >/dev/null 2>&1; then
    echo "Updating existing Production Lambda function code..."
    aws lambda update-function-code --function-name ${LAMBDA_FUNCTION_NAME} --image-uri ${IMAGE_URI}
    
    echo "Waiting for update to complete..."
    aws lambda wait function-updated --function-name ${LAMBDA_FUNCTION_NAME}

    echo "Updating environment variables..."
    aws lambda update-function-configuration \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --environment "Variables={${ENV_VARS}}"

else
    echo "Production Lambda function ${LAMBDA_FUNCTION_NAME} not found. Please create it or check the name."
    exit 1
fi

echo "Production Deployment completed!"
echo "Production Function URL:"
aws lambda get-function-url-config --function-name ${LAMBDA_FUNCTION_NAME} --query FunctionUrl --output text
