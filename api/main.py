import sys
import os
from pathlib import Path

# Add project root to path so backend modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.session_manager import SessionManager

from starlette.middleware.sessions import SessionMiddleware
from api.auth import router as auth_router
from api.db import get_user_policies, create_policy, update_policy, delete_policy
from api.parser import extract_text_from_pdf, parse_policy_with_llm, save_policy_files

app = FastAPI(title="Insurance Consultant API")

# Add Session Middleware
SECRET_KEY = os.getenv("SESSION_SECRET", "a-very-secret-session-key")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")

session_manager = SessionManager()

# --- Policy Management Endpoints ---

@app.get("/api/policies")
async def list_policies(request: Request):
    # Using Request for HTTP calls, but supporting both if needed
    if isinstance(request, Request):
        user = request.session.get("user")
        if not user:
            return {"error": "Not authenticated", "policies": []}
        policies = get_user_policies(user["id"])
        return {"policies": policies}
    return {"error": "Invalid request type"}

@app.post("/api/policies")
async def add_policy(request: Request):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
    data = await request.json()
    new_policy = create_policy(user["id"], data)
    return {"success": True, "policy": new_policy}

@app.put("/api/policies/{policy_id}")
async def edit_policy(policy_id: int, request: Request):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
    data = await request.json()
    success = update_policy(policy_id, user["id"], data)
    return {"success": success}

@app.delete("/api/policies/{policy_id}")
async def remove_policy(policy_id: int, request: Request):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
    success = delete_policy(policy_id, user["id"])
    return {"success": success}

@app.post("/api/policies/parse")
async def parse_policy(request: Request, file: UploadFile = File(...)):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
        
    temp_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"upload_{uuid.uuid4()}_{file.filename}")
    
    try:
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        
        # 1. Extract text using docling
        md_text = extract_text_from_pdf(Path(temp_path))
        if not md_text:
            return {"error": "Failed to extract text from PDF"}
            
        # 2. Extract structured data using LLM
        parsed_data = parse_policy_with_llm(md_text)
        
        # 3. Save to library if not duplicate
        insurer = parsed_data.get("insurer", "unknown")
        policy_name = parsed_data.get("insurance_name", file.filename)
        
        # Ensure name exists for the library storage
        if not parsed_data.get("insurance_name"):
            parsed_data["insurance_name"] = policy_name
            
        pdf_rel_path = save_policy_files(Path(temp_path), insurer, policy_name, md_text)
        
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return {
            "success": True,
            "data": parsed_data,
            "document_url": pdf_rel_path or ""
        }
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return {"error": f"Parsing failed: {e}"}

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
                # Fetch user context for the workflow
                user_profile = None
                existing_policies = []
                
                # Check for user in request session
                from api.db import get_user_by_email, get_user_policies
                user_session = websocket.session.get("user")
                if user_session and user_session.get("email"):
                    full_user = get_user_by_email(user_session["email"])
                    if full_user:
                        user_profile = dict(full_user)
                        existing_policies = get_user_policies(full_user["id"])
                
                asyncio.create_task(
                    session_manager.run_workflow(
                        session_id, 
                        data["message"], 
                        loop,
                        user_profile=user_profile,
                        existing_policies=existing_policies
                    )
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
