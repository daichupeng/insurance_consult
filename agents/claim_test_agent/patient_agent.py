from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

def generate_patient_response(test_state, messages, llm):
    """
    Generate a response from the simulated patient.
    """
    scenario_output = test_state.get('scenario_output', '')
    
    system_prompt = f"""You are a patient interacting with an AI insurance claim agent.
Your goal is to answer the agent's questions based on your scenario facts.
Do NOT reveal your underlying ground truth medical diagnosis directly unless the scenario says you know it (e.g. stage is post-consulting).
Just describe your symptoms and situation as stated in the scenario.

Scenario Facts:
{scenario_output}

Keep your answers concise and natural, like a real person chatting.
Do NOT output any internal thoughts or JSON, just the text response.
"""
    
    # We must only pass the conversation history, but we need to ensure roles are correct.
    # The claim agent's messages are "assistant" (AIMessage), patient's are "user" (HumanMessage).
    # But from the patient agent's perspective, it is the user. So it generates a HumanMessage.
    
    langchain_messages = [SystemMessage(content=system_prompt)]
    for msg in messages:
        if isinstance(msg, AIMessage):
            langchain_messages.append(HumanMessage(content=msg.content)) # to the patient LLM, the claim agent is the user? Wait, no.
            # Actually, standard is: the claim agent is the assistant, so from patient LLM perspective, it's the assistant?
            # It's better to treat the claim agent as the "user" talking to the patient "assistant", OR
            # Just keep it standard: Claim agent is assistant, Patient is user.
            # To prompt the LLM to act as the user, we can pass Claim Agent as assistant, Patient as user, 
            # and ask the LLM to complete the next user message. Wait, LLMs are tuned to reply as Assistant.
            # So from the LLM's perspective, the Patient is the Assistant!
            pass
            
    # Let's map roles for the patient LLM:
    # Claim Agent (assistant) -> HumanMessage (User asking patient)
    # Patient (user) -> AIMessage (Patient answering)
    for msg in messages:
        role = ""
        content = ""
        if isinstance(msg, (HumanMessage, AIMessage, SystemMessage)):
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            content = msg.content
        elif isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        
        if role == "assistant":
            langchain_messages.append(HumanMessage(content=content))
        elif role == "user":
            langchain_messages.append(AIMessage(content=content))
            
    response = llm.invoke(langchain_messages)
    return response.content
