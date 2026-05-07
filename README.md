# Insurance Consult

A web application and LLM-powered RAG system for insurance consultation.

The systme uses:
- Docling for document parsing
- Qdrant for vector storage
- MLX Qwen Embeddings for embedding
- LangGraph for agent orchestration

0309 
    done:
    - User requirement gathering. Using fixed schema
    - Dynamic criteria generation
    - Retrieve context for filters and criteria
    - Policy scoring based on retrieced contexts

    todo:
    - RAG embedding optimization. graphRAG??
    - Retrieval tools optimization: tools optimization; reflection

    - Criteria generation optimization: reflexion. Do few-shot.
    - Dynamic user requirement

    - Policy scoring process: to further break down tasks


0318
    done:
    - RAG indexing for tables
    - Criteria reflection
    - Retrieval reflection

    todo:
    - GraphRAG
    - For criteria generation, further optimize. Think of how to evaluate the quality of criteria generation.
    - Improve retrieval efficiency and relevance

    - Scoring: introduce more tools
        - Premium calculation
        - Other scoring tools
        - Maybe ask agent to write code for scoring if needed


0326
    done:
    - GraphRAG. 
    - Dynamic crawling policie documents
    - Dynamic requirements
    
    todo:
    - Requirements are quite rigid. The consultant is not functioning as an advisor but just a information gatherer
    - Criteria generator is ok but can further optimize. Especially the economic criteria should be more straightforward
    - Policy fetcher can fetch more information for later processing
    - Retriever and Scorer needs more optimization:
        - Access to more information from comparefirst
        - More flexible tools for economic calculation
        - Smarter query expansion

    - Individual rating is not consistent
        - Maybe summarize into comparison
        - Score basedd on comparison table
        - Summarize into a big table, before scoring wholistically

    - Cache graphrag queries

    - Cache user requirement queries

    - user in the loop to ask more questions

    - Scenarios to run

0402
    done:
    - Economics return calculation
    - Comparison table
    - User followup

    todo:
    - Cache queries "memory"
    - Use markdown instead of GraphRAG
    - Optimize prompts: try few-shot, try planner. Langgraph todo agent.
    - Orchestrator to decide whether to invoke the chatagent or the recommendation agent
    - User management (phase 2)

0408
    todo:
    - Build a reviewer system to run the system, simulate user, and evaluate the system - build a closed loop evaluation system. Different user personas, and generate relevant questions for evaluation.
    - Explain the reason for suggesting the critieria and filters
    - Consider using SFTed small LLM for certain parts of the workflow. Focus on specific knowledge and reasoning capability of the models
    - Compare current policy vs new ones
    - Save chat sessions
    - Build claiming agent


0428:
    done:
    - Claim agent initial. Currently focused on claiming plan given some assumptions.
    - Orchestrator between multiple agents: claim, new insurance, query
    - Testing scenarios. https://docs.google.com/spreadsheets/d/1FMsgWa_ZM5RyYv52PZ87Xh8L7PnbRmQWq-lFIaTl5Eg/edit?gid=1741521850#gid=1741521850

    todo:
    - Save chat sessions
    - Refine claim agent, especially claiming proposal subagent. Build a treatment plan subagent.
    - Auto-review system
    - memory 持久化。短期记忆：md，给agent search功能
    - md policy use search tool for agent