from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

def generate_patient_response(test_state, messages, llm):
    """
    Generate a response from the simulated patient.
    """
    scenario_output = test_state.get('scenario_output', '')
    costs = test_state.get('costs', '')
    
    system_prompt = f"""You are a patient interacting with an AI insurance claim agent.
Your goal is to answer the agent's questions based on your scenario facts.
Do NOT reveal your underlying ground truth medical diagnosis directly unless the scenario says you know it .
Just describe your symptoms and situation as stated in the scenario.

Scenario Facts:
{scenario_output}
Already incurred costs: 
{costs}

Keep your answers concise and natural, like a real person chatting.å
"""
    
    # We must only pass the conversation history, but we need to ensure roles are correct.
    # The claim agent's messages are "assistant" (AIMessage), patient's are "user" (HumanMessage).
    # But from the patient agent's perspective, it is the user. So it generates a HumanMessage.
    
    langchain_messages = [SystemMessage(content=system_prompt)]
    for msg in messages:
        if isinstance(msg, AIMessage):
            langchain_messages.append(HumanMessage(content=msg.content)) 
            
    # Let's map roles for the patient LLM:
    # Claim Agent (AIMessage) -> HumanMessage (User asking patient)
    # Patient (HumanMessage) -> AIMessage (Patient answering)
    for msg in messages:
        if isinstance(msg, AIMessage):
            langchain_messages.append(HumanMessage(content=msg.content))
        elif isinstance(msg, HumanMessage):
            langchain_messages.append(AIMessage(content=msg.content))
            
    response = llm.invoke(langchain_messages)
    return response.content
