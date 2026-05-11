import sys

content = open("api/session_manager.py").read()

def insert_methods():
    target = """class SessionManager:
    def __init__(self):
        self.sessions: dict[str, Session] = {}"""
    replacement = """class SessionManager:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        
    def _save_state(self, session):
        try:
            from api.db import update_conversation
            state_data = {
                "user_requirements": session.user_requirements,
                "criteria": session.criteria,
                "policies": session.policies,
            }
            safe_claim_state = {}
            for k, v in session.claim_state.items():
                if k not in ["messages", "analyzer_state"]:
                    if isinstance(v, list):
                        safe_claim_state[k] = [x.model_dump() if hasattr(x, "model_dump") else (x if isinstance(x, (dict, str, int, float, bool)) else str(x)) for x in v]
                    else:
                        safe_claim_state[k] = v if isinstance(v, (dict, str, int, float, bool, type(None))) else str(v)
            state_data["claim_state"] = safe_claim_state
            
            title = "New Conversation"
            if session.user_requirements and getattr(session.user_requirements, "get", lambda x: None)("name"):
                title = f"Advice for {session.user_requirements.get('name')}"
                
            update_conversation(session.session_id, session.phase, state_data, title)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _save_message(self, session_id, role, msg_type, content, raw_data):
        try:
            from api.db import add_message
            add_message(session_id, role, msg_type, content, raw_data)
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
"""
    return content.replace(target, replacement)

def modify_send(content, fn_name, new_send):
    # This searches for `def send(update: dict):` inside specific functions and updates them.
    # We can just replace all occurrences of `def send(update: dict):` and its body with `new_send`
    pass

new_content = insert_methods()

# Replace send function in run_workflow
target1 = """        def send(update: dict):
            if update.get("type") in ["question", "complete", "error"]:
                session.messages.append({"role": "assistant", "content": update.get("message") or update.get("content") or ""})
            asyncio.run_coroutine_threadsafe(
                session.updates_queue.put(update), loop
            ).result()"""

replacement1 = """        def send(update: dict):
            if update.get("type") in ["question", "complete", "error"]:
                session.messages.append({"role": "assistant", "content": update.get("message") or update.get("content") or ""})
            self._save_message(session_id, "assistant", update.get("type", "unknown"), update.get("message") or update.get("content") or "", update)
            self._save_state(session)
            asyncio.run_coroutine_threadsafe(
                session.updates_queue.put(update), loop
            ).result()"""

new_content = new_content.replace(target1, replacement1)

# Handle message saving for user message
target2 = """        # Track history
        session.messages.append({"role": "user", "content": user_message})"""

replacement2 = """        # Track history
        session.messages.append({"role": "user", "content": user_message})
        self._save_message(session_id, "user", "user", user_message, {"type": "user", "content": user_message})"""

new_content = new_content.replace(target2, replacement2)

with open("api/session_manager.py", "w") as f:
    f.write(new_content)

