# AWS Lambda公式のPythonイメージを使用
FROM public.ecr.aws/lambda/python:3.11

# 依存関係をインストール
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . ${LAMBDA_TASK_ROOT}

# Lambdaハンドラーを指定
CMD [ "main.handler" ]
