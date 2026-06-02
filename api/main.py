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
from api.db import (
    init_db,
    get_user_policies, create_policy, update_policy, delete_policy,
    get_user_conversations, get_conversation, create_conversation, 
    get_conversation_messages, delete_conversation, update_conversation_title
)
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
init_db()

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

@app.post("/api/test_claim/random")
async def get_random_test_scenario(request: Request):
    from langchain_openai import ChatOpenAI
    from agents.claim_test_agent.random_scenario import generate_random_scenario
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.8, api_key=os.getenv("OPENAI_API_KEY"))
    scenario = generate_random_scenario(llm)
    return scenario.model_dump()

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
async def create_session(request: Request):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
    
    # Check if a type was provided in the JSON body
    try:
        data = await request.json()
        conv_type = data.get("type", "advice")
    except:
        conv_type = "advice"
        
    session_id = str(uuid.uuid4())
    create_conversation(session_id, user["id"], title="New Conversation", session_type=conv_type)
    session_manager.create_session(session_id)
    return {"session_id": session_id}

@app.get("/api/conversations")
async def list_conversations(request: Request, type: str = None):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated", "conversations": []}
    convs = get_user_conversations(user["id"], session_type=type)
    return {"conversations": convs}

@app.delete("/api/conversations/{session_id}")
async def remove_conversation(session_id: str, request: Request):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
    success = delete_conversation(session_id, user["id"])
    return {"success": success}

@app.put("/api/conversations/{session_id}/title")
async def rename_conversation(session_id: str, request: Request):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
    data = await request.json()
    if "title" in data:
        update_conversation_title(session_id, data["title"])
        return {"success": True}
    return {"error": "Missing title"}

@app.get("/api/conversations/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    user = request.session.get("user")
    if not user:
        return {"error": "Not authenticated"}
    msgs = get_conversation_messages(session_id)
    return {"messages": msgs}


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


def _policy_from_crawled(cd: dict) -> dict:
    """Build a minimal Policy-shaped dict from a crawled policy entry.

    Used when the user asks to build a simulator for a policy that wasn't in
    the top-N (so it never went through retrieval / info extraction). The
    scenario coder will fall back to its read_policy_section tool because
    key_info is empty.
    """
    return {
        "policy_name": cd.get("policy_name", ""),
        "basic_info": {
            "insurer": cd.get("insurer", ""),
            "sub_type": cd.get("sub_type", ""),
            "sub_information": cd.get("sub_information", ""),
            "annual_premium": cd.get("annual_premium", "N/A"),
            "coverage_term_years": cd.get("coverage_term_years", "N/A"),
            "premium_term_years": cd.get("premium_term_years", "N/A"),
            "total_premium": cd.get("total_premium", "N/A"),
            "distribution_cost": cd.get("distribution_cost", "N/A"),
            "credit_rating": cd.get("credit_rating", "N/A"),
            "guaranteed_maturity_benefit": cd.get("guaranteed_maturity_benefit", "N/A"),
            "product_summary_url": cd.get("product_summary_url", ""),
            "brochure_url": cd.get("brochure_url", ""),
        },
        "return_rate": float(cd.get("return_rate") or 0.0),
        "fulfil_filters": (True, "Not evaluated (not in top-N)"),
        "scoring": [],
        "retrieved_context": {},
        "context_summary": {},
        "policy_document": "",
        "key_info": None,
    }


@app.post("/api/simulator/prepare")
async def simulator_prepare(payload: dict):
    """Generate (or load cached) simulator code for a policy and return its
    INPUT / OUTPUT schemas.

    Body: {"session_id": "...", "policy_name": "...", "force": false}
    """
    session_id = payload.get("session_id")
    policy_name = payload.get("policy_name")
    force = bool(payload.get("force", False))
    if not session_id or not policy_name:
        return {"error": "session_id and policy_name required"}

    session = session_manager.get_session(session_id)
    if not session:
        return {"error": "Session not found"}

    # Prefer the scored / info-extracted entry (top-N); fall back to the raw
    # crawled record for any other policy.
    policy_dict = next(
        (p for p in (session.policies or []) if p.get("policy_name") == policy_name),
        None,
    )
    if policy_dict is None:
        crawled = next(
            (p for p in (session.crawled_policies or []) if p.get("policy_name") == policy_name),
            None,
        )
        if crawled is None:
            return {"error": f"Policy '{policy_name}' not found in session"}
        policy_dict = _policy_from_crawled(crawled)

    from agents.new_life_insurance.scenario_coder import (
        ScenarioCoder, codebank_path, load_schemas,
    )
    from schema.models import Policy

    target = codebank_path(policy_name)
    if force or not target.exists():
        try:
            policy = Policy(**policy_dict)
        except Exception as e:
            return {"error": f"Policy decode failed: {e}"}
        try:
            await asyncio.to_thread(ScenarioCoder().generate, policy, force)
        except Exception as e:
            return {"error": f"Generation failed: {e}"}

    return load_schemas(policy_name)


@app.post("/api/simulator/run")
async def simulator_run(payload: dict):
    """Execute a cached simulator with user-provided inputs.

    Body: {"policy_name": "...", "inputs": { ... }}
    """
    policy_name = payload.get("policy_name")
    if not policy_name:
        return {"error": "policy_name required"}

    from agents.new_life_insurance.scenario_coder import run_simulator
    return await asyncio.to_thread(run_simulator, policy_name, payload.get("inputs") or {})


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    session = session_manager.get_session(session_id)
    if not session:
        # Try to load from DB
        conv = get_conversation(session_id)
        if not conv:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Session not found"})
            )
            await websocket.close()
            return
        
        session = session_manager.create_session(session_id)
        # Load state from DB
        session.phase = conv.get("phase", "idle")
        session.advice_entity = conv.get("advice_entity")
        state = conv.get("state_data", {})
        session.user_requirements = state.get("user_requirements")
        session.criteria = state.get("criteria")
        session.policies = state.get("policies", [])
        session.claim_state = state.get("claim_state", session.claim_state)
        # Load messages to orchestrator context
        db_msgs = get_conversation_messages(session_id)
        for m in db_msgs:
            if m["role"] in ["user", "assistant"]:
                session.messages.append({"role": m["role"], "content": m["content"]})

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
            
            # Fetch user context for the workflow
            user_profile = None
            existing_policies = []
            from api.db import get_user_by_email, get_user_policies
            user_session = websocket.session.get("user")
            if user_session and user_session.get("email"):
                full_user = get_user_by_email(user_session["email"])
                if full_user:
                    user_profile = dict(full_user)
                    existing_policies = get_user_policies(full_user["id"])
                    
            # Extract content based on legacy frontend payload structure
            if data["type"] == "start":
                message_content = data.get("message", "")
            elif data["type"] == "answer":
                message_content = data.get("content", "")
            else:
                message_content = data.get("message", data.get("content", ""))

            # Pass to orchestrator instead of hardcoded routing
            if data["type"] == "start_test":
                asyncio.create_task(
                    session_manager.run_test_claim_workflow(
                        session_id,
                        data.get("params", {}),
                        loop
                    )
                )
            elif data["type"] == "confirm_params":
                # Structured answer: hand the edited crawler params straight back
                # to the waiting fetcher thread without going through the LLM
                # intent classifier.
                _sess = session_manager.get_session(session_id)
                if _sess:
                    _sess.set_answer(json.dumps(data.get("params", {})))
            else:
                asyncio.create_task(
                    session_manager.handle_message(
                        session_id, 
                        message_content, 
                        loop,
                        user_profile=user_profile,
                        existing_policies=existing_policies
                    )
                )
    except WebSocketDisconnect:
        pass
    finally:
        update_task.cancel()


# Serve static files for policy documents
_raw_policies_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw_policies"
)
app.mount("/raw_policies", StaticFiles(directory=_raw_policies_dir), name="raw_policies")

# Serve frontend - must be registered last
_frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
