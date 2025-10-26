FROM public.ecr.aws/docker/library/python:3.12.0-slim-bullseye

# Lambda Adapter 拡張
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.0 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app
ADD . .
RUN pip install -r requirements.txt

# Lambda adapter設定
ENV AWS_LWA_INVOKE_MODE RESPONSE_STREAM

# uvicornでFastAPI起動
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
