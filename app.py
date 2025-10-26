import os
import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain.agents import create_react_agent
from langchain_aws import ChatBedrock
import dotenv

dotenv.load_dotenv()

# -------------------------
# Lazy Init（遅延初期化）
# -------------------------
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
        _agent = create_react_agent(llm, tools)
    return _agent

# -------------------------
# FastAPI アプリ
# -------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# 共通処理ロジック
# -------------------------
async def handle_post(request: Request):
    agent = await get_agent()
    body = await request.json()
    messages = body.get("messages", [])

    async def event_stream():
        async for event in agent.astream_events({"messages": messages}, version="v1"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                delta = event["data"]["chunk"].content
                if delta:
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
                if isinstance(tool_output, dict) and tool_output.get("type") == "chart":
                    yield f"data: {json.dumps({'type': 'chart', 'tool_name': event['name'], 'tool_response': tool_output, 'tool_id': event['run_id'], 'chart': tool_output}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool_name': event['name'], 'tool_response': tool_output, 'tool_id': event['run_id']}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# -------------------------
# すべての POST を `/` に集約
# -------------------------
@app.post("/{full_path:path}")
async def catch_all_post(full_path: str, request: Request):
    return await handle_post(request)