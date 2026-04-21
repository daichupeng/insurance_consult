import asyncio
import logging
import time
import threading
import os
from typing import Optional, Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.updates_queue: asyncio.Queue = asyncio.Queue()
        self._answer_event = threading.Event()
        self._answer_value: Optional[str] = None
        self.phase = "idle"
        self.user_requirements: Optional[dict] = None
        self.user_profile: Optional[dict] = None
        self.existing_policies: list = []
        self.criteria: Optional[dict] = None
        self.crawled_policies: list = []
        self.policies: list = []
        self.query_agent: Optional[Any] = None
        self.active_agent: Optional[str] = None
        self.cancel_event = threading.Event()
        self.claim_state: dict = {
            "messages": [],
            "claim_scenario": "",
            "claim_details": {},
            "relevant_policies": [],
            "claim_strategy": "",
            "missing_info": True,
            "review_status": ""
        }
        
        # Lazy load orchestrator
        self._orchestrator = None
        
    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from agents.orchestrator import Orchestrator
            self._orchestrator = Orchestrator()
        return self._orchestrator

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
        user_profile: Optional[dict] = None,
        existing_policies: Optional[list] = None,
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
                from agents.new_life_insurance.profile_analyzer import ProfileAnalyzer
                from agents.new_life_insurance.criteria_generator import CriteriaGenerator
                from agents.new_life_insurance.policy_fetcher import PolicyFetcher
                from agents.new_life_insurance.summarizer import PolicySummarizer
                from agents.new_life_insurance.policy_scorer import PolicyScorer

                # Retriever backend selection
                load_dotenv()
                backend = os.getenv("RETRIEVER_BACKEND", "md").lower()
                if backend == "graphrag":
                    from agents.new_life_insurance.graph_rag_retriever import GraphRAGRetriever as _RetrieverClass
                    logger.info("[Session %s] Using GraphRAG retriever backend.", session_id)
                    print(f"\n[Session {session_id}] Using GraphRAG retriever backend.")
                else:
                    from agents.new_life_insurance.md_retriever import MDRetriever as _RetrieverClass
                    logger.info("[Session %s] Using MD retriever backend.", session_id)
                    print(f"\n[Session {session_id}] Using MD retriever backend.")

                profile_analyzer = ProfileAnalyzer(confirm_callback=confirm_callback)
                criteria_generator = CriteriaGenerator()
                policy_fetcher = PolicyFetcher()
                retriever = _RetrieverClass()
                summarizer_agent = PolicySummarizer()
                policy_scorer = PolicyScorer()

                session.user_profile = user_profile
                session.existing_policies = existing_policies or []
                
                # Phase 1: Profile
                if session.cancel_event.is_set(): return
                session.phase = "profile"
                print(f"[DEBUG] [Session {session_id}] Phase 1: profile start")
                send({"type": "status", "phase": "profile", "message": "Gathering your insurance requirements..."})
                session.active_agent = "new_life_insurance"
                t0 = time.perf_counter()
                profile, _ = profile_analyzer.analyze_profile(
                    user_message, 
                    user_profile=user_profile,
                    existing_policies=existing_policies
                )
                print(f"[DEBUG] [Session {session_id}] Phase 1: profile complete")
                logger.info("[Session %s] Phase 1 profile: %.2fs", session_id, time.perf_counter() - t0)
                session.user_requirements = profile.model_dump()
                send({"type": "requirements", "data": session.user_requirements})

                # Phase 2: Criteria
                if session.cancel_event.is_set(): return
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
                if session.cancel_event.is_set(): return
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
                if session.cancel_event.is_set(): return
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
                    crawled_policies=crawled_policies,
                )
                logger.info("[Session %s] Phase 4 retrieval: %.2fs  (%d policies)",
                            session_id, time.perf_counter() - t0, len(policies))

                # Phase 4.5: Summarization
                if session.cancel_event.is_set(): return
                session.phase = "summarization"
                send({"type": "status", "phase": "summarization", "message": "Summarizing retrieved contexts..."})
                t0 = time.perf_counter()
                policies = summarizer_agent.summarize_policies(policies, criteria)
                logger.info("[Session %s] Phase 4.5 summarization: %.2fs", session_id, time.perf_counter() - t0)

                # Phase 5: Scoring
                if session.cancel_event.is_set(): return
                session.phase = "scoring"
                send({"type": "status", "phase": "scoring", "message": "Evaluating and scoring all policies..."})
                t0 = time.perf_counter()
                scored_policies = policy_scorer.score_policies(policies, criteria)
                logger.info("[Session %s] Phase 5 scoring: %.2fs", session_id, time.perf_counter() - t0)
                session.policies = [p.model_dump() for p in scored_policies]
                send({"type": "policies", "data": session.policies})

                if session.cancel_event.is_set(): return
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

    async def run_query(
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

        def run():
            t0 = time.perf_counter()
            try:
                # Lazy load the query agent to save memory if unused
                if session.query_agent is None:
                    from agents.query_agent import QueryAgent
                    session.query_agent = QueryAgent()

                response = session.query_agent.answer_query(
                    query=user_message,
                    requirements=session.user_requirements,
                    criteria=session.criteria,
                    policies=session.policies,
                )
                logger.info("[Session %s] Query answered in %.2fs", session_id, time.perf_counter() - t0)
                send({"type": "question", "content": response})

            except Exception as e:
                import traceback
                logger.error("[Session %s] Query error after %.2fs: %s",
                             session_id, time.perf_counter() - t0, e, exc_info=True)
                send({
                    "type": "error",
                    "message": f"Query failed: {str(e)}",
                    "detail": traceback.format_exc(),
                })

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    async def run_claim_workflow(
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

        def run():
            from graphs.claim_agent.workflow import claim_agent_workflow
            from langchain_core.messages import HumanMessage
            
            t_workflow = time.perf_counter()
            send({"type": "status", "phase": "processing", "message": "Analyzing claim details..."})
            try:
                session.claim_state["messages"].append(HumanMessage(content=user_message))
                
                # Execute graph
                final_state = claim_agent_workflow.invoke(session.claim_state)
                
                # Sync state back
                session.claim_state.update(final_state)
                
                if final_state.get("missing_info"):
                    # The graph output a clarification message
                    last_msg = final_state["messages"][-1]
                    # We expect dict from state, extract content correctly whether it's dict or object
                    content = last_msg.get("content", "") if isinstance(last_msg, dict) else last_msg.content
                    send({"type": "question", "content": content})
                    session.phase = "processing"
                else:
                    strategy = final_state.get("claim_strategy", "No strategy was generated.")
                    send({"type": "status", "phase": "complete", "message": "Claim analysis complete."})
                    send({"type": "question", "content": f"Here is your recommended claiming strategy:\n\n{strategy}"})
                    session.phase = "idle"
                    # reset state for next claim
                    session.claim_state = {
                        "messages": [], "claim_scenario": "", "claim_details": {},
                        "relevant_policies": [], "claim_strategy": "",
                        "missing_info": True, "review_status": ""
                    }
                    
            except Exception as e:
                import traceback
                logger.error("[Session %s] Claim Error: %s", session_id, e, exc_info=True)
                send({"type": "error", "message": str(e), "detail": traceback.format_exc()})
                
        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    async def handle_message(
        self,
        session_id: str,
        user_message: str,
        loop: asyncio.AbstractEventLoop,
        user_profile: Optional[dict] = None,
        existing_policies: Optional[list] = None,
    ):
        session = self.get_session(session_id)
        if not session:
            return

        async def async_send(update: dict):
            await session.updates_queue.put(update)

        # Step 1: Evaluate Orchestration (wrapped in to_thread since it uses sync LLM invokes)
        result = await asyncio.to_thread(
            session.orchestrator.evaluate_input, 
            user_message, session.active_agent, session.phase
        )
        
        # Step 2: Input Sanitization / Security
        if not result.is_valid:
            logger.warning(f"[Session {session_id}] Orchestrator rejected input: {result.reasoning}")
            await async_send({"type": "error", "message": "I'm sorry, I cannot process that request. Please keep the conversation focused on insurance consultation."})
            return

        logger.info(f"[Session {session_id}] Action={result.intent_type}, Target={result.target_agent}")

        # Step 3: Handle Global Commands
        if result.intent_type == "global_command":
            cmd = (result.extracted_command or "").lower()
            if "start" in cmd or "clear" in cmd or "reset" in cmd:
                session.cancel_event.set()
                # Create a fresh session state but keep the ID
                self.sessions[session_id] = Session(session_id)
                await async_send({"type": "complete", "message": "Session has been reset. How can I help you today?"})
            else:
                await async_send({"type": "question", "content": "I am your AI Insurance Consultant. I can help you find new life insurance or answer insurance questions. What would you like to do?"})
            return

        # Step 4: Handle Terminal Interruption
        if result.intent_type == "terminal_interruption":
            session.cancel_event.set()
            await async_send({"type": "status", "phase": "interrupted", "message": "Stopping previous task..."})
            
            # Start fresh for the new task
            session.cancel_event = threading.Event()
            session.active_agent = result.target_agent
            session.phase = "idle"
            
            if session.active_agent == "new_life_insurance":
                asyncio.create_task(self.run_workflow(session_id, user_message, loop, user_profile, existing_policies))
            elif session.active_agent == "claiming_strategy":
                asyncio.create_task(self.run_claim_workflow(session_id, user_message, loop))
            else:
                asyncio.create_task(self.run_query(session_id, user_message, loop))
            return

        # Step 5: Handle Transient Interruption
        if result.intent_type == "transient_interruption":
            # Answer quickly with query agent without breaking the main flow
            if session.query_agent is None:
                from agents.query_agent import QueryAgent
                session.query_agent = QueryAgent()
            
            async def run_transient():
                try:
                    # Bypass context injection for pure side questions to keep it fast
                    response = await asyncio.to_thread(
                        session.query_agent.agent_executor.invoke, 
                        {"messages": [("user", user_message)]}
                    )
                    answer = response["messages"][-1].content
                    
                    # Output Arbitration
                    is_safe = await asyncio.to_thread(session.orchestrator.validate_output, answer)
                    if not is_safe:
                        answer = "I'm sorry, I cannot provide that information."
                    
                    await async_send({"type": "question", "content": answer + "\n\n*(Now, where were we?)*"})
                except Exception as e:
                    logger.error(f"[Session {session_id}] Transient query error: {e}")
                    await async_send({"type": "error", "message": "Sorry, I couldn't process your side question."})
                    
            asyncio.create_task(run_transient())
            return

        # Step 6: Continue Flow
        if result.intent_type == "continue_flow":
            if session.phase == "idle" or result.target_agent == "new_life_insurance":
                if session.phase in ["idle", "complete", "error", "interrupted"]:
                    asyncio.create_task(self.run_workflow(session_id, user_message, loop, user_profile, existing_policies))
                else:
                    session.set_answer(user_message)
            elif result.target_agent == "claiming_strategy":
                session.phase = "processing"
                asyncio.create_task(self.run_claim_workflow(session_id, user_message, loop))
            else:
                asyncio.create_task(self.run_query(session_id, user_message, loop))
