#!/bin/bash
set -e

# 設定
AWS_REGION="ap-northeast-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="utsulog-api"
IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:latest"
LAMBDA_FUNCTION_NAME="utsulog-api-lambda"

echo "Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo "Building Docker image..."
docker build --platform linux/amd64 -t ${ECR_REPO_NAME} -f Dockerfile.lambda .

echo "Tagging image..."
docker tag ${ECR_REPO_NAME}:latest ${IMAGE_URI}

echo "Pushing image to ECR..."
docker push ${IMAGE_URI}

echo "Updating Lambda function..."
# Lambda関数が存在するか確認
if aws lambda get-function --function-name ${LAMBDA_FUNCTION_NAME} >/dev/null 2>&1; then
    echo "Updating existing Lambda function code..."
    aws lambda update-function-code --function-name ${LAMBDA_FUNCTION_NAME} --image-uri ${IMAGE_URI}
    
    # 更新が完了するまで待機
    echo "Waiting for update to complete..."
    aws lambda wait function-updated --function-name ${LAMBDA_FUNCTION_NAME}
else
    echo "Creating new Lambda function..."
    # 実行ロールのARNを取得 (既存のecsTaskExecutionRoleを流用するか、新規作成が必要だが、ここでは簡易的に既存のものを指定する例。本来はLambda専用ロールが良い)
    # 注: ユーザー環境に合わせてロールARNは確認・変更が必要かもしれません。
    # 一旦、既存のロールを探して設定します。
    ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/utsulog-api-lambda-role"
    
    # ロールが存在しない場合のフォールバック（エラーになる可能性あり）
    if ! aws iam get-role --role-name utsulog-api-lambda-role >/dev/null 2>&1; then
        echo "Creating IAM role for Lambda..."
        aws iam create-role --role-name utsulog-api-lambda-role --assume-role-policy-document '{"Version": "2012-10-17","Statement": [{ "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}'
        aws iam attach-role-policy --role-name utsulog-api-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
        sleep 10 # ロール作成後の伝播待ち
        ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/utsulog-api-lambda-role"
    fi

    aws lambda create-function \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --package-type Image \
        --code ImageUri=${IMAGE_URI} \
        --role ${ROLE_ARN} \
        --timeout 30 \
        --memory-size 512

    echo "Creating Function URL..."
    aws lambda create-function-url-config \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --auth-type NONE
        # CORS設定はFastAPI側で行うため、ここでは設定しない (重複エラー防止)
        
    echo "Adding permission for public access..."
    aws lambda add-permission \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --statement-id FunctionURLAllowPublicAccess \
        --action lambda:InvokeFunctionUrl \
        --principal "*" \
        --function-url-auth-type NONE
fi

echo "Deployment completed!"
echo "Function URL:"
aws lambda get-function-url-config --function-name ${LAMBDA_FUNCTION_NAME} --query FunctionUrl --output text
