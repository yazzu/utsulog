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
ENV_FILE=".env.prod"

# .envファイルから環境変数を読み込む関数
# コメントや空行を無視して、KEY=VALUE形式で変数を読み込む
load_env_vars() {
    local env_file=$1
    local env_vars=""
    while IFS='=' read -r key value || [ -n "$key" ]; do
        # コメント(#)で始まる行と空行をスキップ
        if [[ $key =~ ^# ]] || [[ -z $key ]]; then
            continue
        fi
        # 行末のコメントを削除等は簡易的な処理では行わないが、.env.prodの形式に合わせる
        # 値の前後の空白や引用符の除去が必要な場合は適宜追加
        # ここでは単純に KEY=VALUE を Variables={KEY=VALUE,...} の形式に整形するための準備
        
        # Lambdaの予約済み環境変数をスキップ
        if [[ "$key" == "AWS_ACCESS_KEY_ID" ]] || [[ "$key" == "AWS_SECRET_ACCESS_KEY" ]] || [[ "$key" == "AWS_DEFAULT_REGION" ]]; then
            continue
        fi

        if [ -n "$value" ]; then
            env_vars="${env_vars}${key}=${value},"
        fi
    done < "$env_file"
    # 最後のカンマを削除
    echo "${env_vars%,}"
}

echo "Loading environment variables from ${ENV_FILE}..."
ENV_VARS=$(load_env_vars "${ENV_FILE}")

echo "Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo "Building Docker image for Staging..."
docker build --platform linux/amd64 -t ${ECR_REPO_NAME}:${IMAGE_TAG} -f api/Dockerfile.lambda api

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
        --environment "Variables={${ENV_VARS}}"

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
        --environment "Variables={${ENV_VARS}}"

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
