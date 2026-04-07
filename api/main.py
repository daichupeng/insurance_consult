import sys
import os

# Add project root to path so backend modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.session_manager import SessionManager

app = FastAPI(title="Insurance Consultant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_manager = SessionManager()


@app.post("/api/sessions")
async def create_session():
    session_id = str(uuid.uuid4())
    session_manager.create_session(session_id)
    return {"session_id": session_id}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    return {
        "session_id": session_id,
        "phase": session.phase,
        "user_requirements": session.user_requirements,
        "criteria": session.criteria,
        "policies": session.policies,
    }


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    session = session_manager.get_session(session_id)
    if not session:
        await websocket.send_text(
            json.dumps({"type": "error", "message": "Session not found"})
        )
        await websocket.close()
        return

    loop = asyncio.get_event_loop()

    async def forward_updates():
        while True:
            try:
                update = await asyncio.wait_for(
                    session.updates_queue.get(), timeout=30.0
                )
                await websocket.send_text(json.dumps(update, default=str))
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
            except Exception:
                break

    update_task = asyncio.create_task(forward_updates())

    try:
        async for text in websocket.iter_text():
            data = json.loads(text)
            if data["type"] == "start":
                asyncio.create_task(
                    session_manager.run_workflow(session_id, data["message"], loop)
                )
            elif data["type"] == "answer":
                if session.phase == "complete":
                    asyncio.create_task(
                        session_manager.run_query(session_id, data["content"], loop)
                    )
                else:
                    session.set_answer(data["content"])
    except WebSocketDisconnect:
        pass
    finally:
        update_task.cancel()


# Serve frontend - must be registered last
_frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
