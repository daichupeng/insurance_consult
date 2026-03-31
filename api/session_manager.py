import asyncio
import logging
import time
import threading
from typing import Optional, Any

logger = logging.getLogger(__name__)


class Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.updates_queue: asyncio.Queue = asyncio.Queue()
        self._answer_event = threading.Event()
        self._answer_value: Optional[str] = None
        self.phase = "idle"
        self.user_requirements: Optional[dict] = None
        self.criteria: Optional[dict] = None
        self.crawled_policies: list = []
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
            t_workflow = time.perf_counter()
            try:
                from agents.profile_analyzer import ProfileAnalyzer
                from agents.criteria_generator import CriteriaGenerator
                from agents.policy_fetcher import PolicyFetcher
                from agents.graph_rag_retriever import GraphRAGRetriever
                from agents.summarizer import PolicySummarizer
                from agents.policy_scorer import PolicyScorer

                profile_analyzer = ProfileAnalyzer(confirm_callback=confirm_callback)
                criteria_generator = CriteriaGenerator()
                policy_fetcher = PolicyFetcher()
                retriever = GraphRAGRetriever()
                summarizer_agent = PolicySummarizer()
                policy_scorer = PolicyScorer()

                # Phase 1: Profile
                session.phase = "profile"
                send({"type": "status", "phase": "profile", "message": "Gathering your insurance requirements..."})
                t0 = time.perf_counter()
                profile, _ = profile_analyzer.analyze_profile(user_message)
                logger.info("[Session %s] Phase 1 profile: %.2fs", session_id, time.perf_counter() - t0)
                session.user_requirements = profile.model_dump()
                send({"type": "requirements", "data": session.user_requirements})

                # Phase 2: Criteria
                session.phase = "criteria"
                send({"type": "status", "phase": "criteria", "message": "Generating personalised scoring criteria..."})
                t0 = time.perf_counter()
                criteria = criteria_generator.generate_criteria(profile)
                logger.info("[Session %s] Phase 2 criteria: %.2fs  (%d criteria, %d filters)",
                            session_id, time.perf_counter() - t0,
                            len(criteria.criteria or []), len(criteria.filters or []))
                session.criteria = criteria.model_dump()
                send({"type": "criteria", "data": session.criteria})

                # Phase 3: Fetch policies from comparefirst.sg
                session.phase = "fetching"
                send({"type": "status", "phase": "fetching", "message": "Fetching top policies from comparefirst.sg..."})
                t0 = time.perf_counter()

                def on_policy_found(policy_dict):
                    send({"type": "crawled_policy", "data": policy_dict})

                crawled_policies = policy_fetcher.fetch(profile, on_policy_found=on_policy_found)
                logger.info("[Session %s] Phase 3 fetching: %.2fs  (%d policies)",
                            session_id, time.perf_counter() - t0, len(crawled_policies))
                session.crawled_policies = crawled_policies
                send({"type": "crawled_policies", "data": crawled_policies})

                # Phase 4: Retrieval
                session.phase = "retrieval"
                crawled_names = [p["policy_name"] for p in crawled_policies if p.get("policy_name")]
                send({"type": "policies_list", "data": crawled_names or []})
                send({"type": "status", "phase": "retrieval", "message": "Retrieving relevant policy documents..."})
                t0 = time.perf_counter()

                def on_policy_done(policy):
                    send({"type": "policy_partial", "data": policy.model_dump()})

                policies = retriever.retrieve(
                    criteria,
                    on_policy_done=on_policy_done,
                    crawled_policies=crawled_policies or None,
                )
                logger.info("[Session %s] Phase 4 retrieval: %.2fs  (%d policies)",
                            session_id, time.perf_counter() - t0, len(policies))

                # Phase 4.5: Summarization
                session.phase = "summarization"
                send({"type": "status", "phase": "summarization", "message": "Summarizing retrieved contexts..."})
                t0 = time.perf_counter()
                policies = summarizer_agent.summarize_policies(policies, criteria)
                logger.info("[Session %s] Phase 4.5 summarization: %.2fs", session_id, time.perf_counter() - t0)

                # Phase 5: Scoring
                session.phase = "scoring"
                send({"type": "status", "phase": "scoring", "message": "Evaluating and scoring all policies..."})
                t0 = time.perf_counter()
                scored_policies = policy_scorer.score_policies(policies, criteria)
                logger.info("[Session %s] Phase 5 scoring: %.2fs", session_id, time.perf_counter() - t0)
                session.policies = [p.model_dump() for p in scored_policies]
                send({"type": "policies", "data": session.policies})

                session.phase = "complete"
                logger.info("[Session %s] Workflow complete: %.2fs total",
                            session_id, time.perf_counter() - t_workflow)
                send({"type": "complete", "message": "Analysis complete! Review your results in the panels on the right."})

            except Exception as e:
                import traceback
                logger.error("[Session %s] Workflow error after %.2fs: %s",
                             session_id, time.perf_counter() - t_workflow, e, exc_info=True)
                session.phase = "error"
                send({
                    "type": "error",
                    "message": str(e),
                    "detail": traceback.format_exc(),
                })

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
