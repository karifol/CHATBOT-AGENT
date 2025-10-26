import os
import json
import boto3
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain_aws import ChatBedrock
from datetime import datetime, UTC
import dotenv
import ulid

dotenv.load_dotenv()

S3_BUCKET = os.getenv("CHAT_LOG_BUCKET", "your-chat-log-bucket")
s3 = boto3.client("s3", region_name="ap-northeast-1")

_llm = None
_agent = None

async def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatBedrock(
            region_name="ap-northeast-1",
            model="global.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_tokens=1000,
            temperature=0.5,
        )
    return _llm

async def get_agent():
    global _agent
    if _agent is None:
        llm = await get_llm()
        tools = []
        _agent = create_agent(llm, tools)
    return _agent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# POST処理
# -------------------------
async def handle_post(request: Request):
    agent = await get_agent()
    body = await request.json()
    messages = body.get("messages", [])

    # S3用に保存データを集約
    conversation_log = {
        "request_id": str(ulid.new()),
        "timestamp": datetime.now(UTC).isoformat(),
        "user_messages": messages,
        "assistant_messages": "",
    }

    async def event_stream():
        try:
            async for event in agent.astream_events({"messages": messages}, version="v1"):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    delta = event["data"]["chunk"].content
                    if delta:
                        conversation_log["assistant_messages"] += delta
                        yield f"data: {json.dumps({'type': 'token', 'content': delta}, ensure_ascii=False)}\n\n"
                elif kind == "on_tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': event['name'], 'tool_input': event['data']['input'], 'tool_id': event['run_id']}, ensure_ascii=False)}\n\n"
                elif kind == "on_tool_end":
                    tool_output = event["data"]["output"]
                    try:
                        if hasattr(tool_output, "content"):
                            tool_output = json.loads(tool_output.content)
                    except Exception:
                        pass
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool_name': event['name'], 'tool_response': str(tool_output), 'tool_id': event['run_id']}, ensure_ascii=False)}\n\n"
        finally:
            # Streaming完了後（全yield終了後）にS3へ保存
            save_to_s3(conversation_log)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# -------------------------
# S3 保存関数
# -------------------------
def save_to_s3(log: dict):
    try:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"chat_logs/{date_str}/{log['request_id']}.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(log, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"✅ Saved chat log to s3://{S3_BUCKET}/{key}")
    except Exception as e:
        print(f"⚠️ Failed to save chat log: {e}")

# -------------------------
# Catch-all
# -------------------------
@app.post("/{full_path:path}")
async def catch_all_post(full_path: str, request: Request):
    return await handle_post(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8080)