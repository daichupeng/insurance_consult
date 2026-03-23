import asyncio
import threading
from typing import Optional, Any


class Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.updates_queue: asyncio.Queue = asyncio.Queue()
        self._answer_event = threading.Event()
        self._answer_value: Optional[str] = None
        self.phase = "idle"
        self.user_requirements: Optional[dict] = None
        self.criteria: Optional[dict] = None
        self.policies: list = []

    def set_answer(self, answer: str):
        self._answer_value = answer
        self._answer_event.set()

    def wait_for_answer(self, timeout: int = 300) -> Optional[str]:
        self._answer_event.wait(timeout=timeout)
        self._answer_event.clear()
        answer = self._answer_value
        self._answer_value = None
        return answer


class SessionManager:
    def __init__(self):
        self.sessions: dict[str, Session] = {}

    def create_session(self, session_id: str) -> Session:
        session = Session(session_id)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    async def run_workflow(
        self,
        session_id: str,
        user_message: str,
        loop: asyncio.AbstractEventLoop,
    ):
        session = self.get_session(session_id)
        if not session:
            return

        def send(update: dict):
            asyncio.run_coroutine_threadsafe(
                session.updates_queue.put(update), loop
            ).result()

        def confirm_callback(question: str) -> Optional[str]:
            send({"type": "question", "content": question})
            return session.wait_for_answer()

        def run():
            try:
                from agents.profile_analyzer import ProfileAnalyzer
                from agents.criteria_generator import CriteriaGenerator
                from agents.graph_rag_retriever import GraphRAGRetriever
                from agents.policy_scorer import PolicyScorer

                profile_analyzer = ProfileAnalyzer(confirm_callback=confirm_callback)
                criteria_generator = CriteriaGenerator()
                retriever = GraphRAGRetriever()
                policy_scorer = PolicyScorer()

                # Phase 1: Profile
                session.phase = "profile"
                send({"type": "status", "phase": "profile", "message": "Gathering your insurance requirements..."})
                profile, _ = profile_analyzer.analyze_profile(user_message)
                session.user_requirements = profile.model_dump()
                send({"type": "requirements", "data": session.user_requirements})

                # Phase 2: Criteria
                session.phase = "criteria"
                send({"type": "status", "phase": "criteria", "message": "Generating personalised scoring criteria..."})
                criteria = criteria_generator.generate_criteria(profile)
                session.criteria = criteria.model_dump()
                send({"type": "criteria", "data": session.criteria})

                # Phase 3: Retrieval
                session.phase = "retrieval"
                send({"type": "status", "phase": "retrieval", "message": "Retrieving relevant policy documents..."})
                policies = retriever.retrieve(criteria)

                # Phase 4: Scoring
                session.phase = "scoring"
                send({"type": "status", "phase": "scoring", "message": "Evaluating and scoring all policies..."})
                scored_policies = policy_scorer.score_policies(policies, criteria)
                session.policies = [p.model_dump() for p in scored_policies]
                send({"type": "policies", "data": session.policies})

                session.phase = "complete"
                send({"type": "complete", "message": "Analysis complete! Review your results in the panels on the right."})

            except Exception as e:
                import traceback
                session.phase = "error"
                send({
                    "type": "error",
                    "message": str(e),
                    "detail": traceback.format_exc(),
                })

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
