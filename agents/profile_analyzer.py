from schema.models import UserRequirements
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from typing import Tuple, Optional
from tools.interactive_tools import confirm_requirements

import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

class ProfileAnalyzer:
    def __init__(self):
        self.llm_with_tools = llm.bind_tools([confirm_requirements, UserRequirements])
        self.system_prompt = SystemMessage(content=(
             "You are an expert life insurance consultant. Your task is to gather information to build a user's life insurance requirements profile.\n"
             "1. Read the user's initial input and any subsequent responses. If you are missing any essential details, use the `confirm_requirements` tool to ask the user. You can ask multiple clarification questions if needed (you may batch them into a single tool call for a better user experience)\n"
             "2. VALIDATE the user's responses. If a user provides an invalid or unreasonable response, DO NOT accept it. Instead, explain why the input is invalid and use the `confirm_requirements` tool to request that specific piece of information again.\n"
             "3. The user might provide ambiguous responses. If you think the user can't decide on a clear answer, recommend a decision with clear reasoning and ask for confirmation. All items must be explicitly confirmed by user before calling UserRequirements."
        ))

    def analyze_profile(self, user_input: str, existing_profile: Optional[UserRequirements] = None) -> Tuple[UserRequirements, dict]:
        """
        Runs an agentic loop to extract the profile from the user input.
        If information is missing, it will pause and prompt the user via the command line tool.
        """
        messages = [self.system_prompt]
        
        if existing_profile:
            profile_dict = existing_profile.model_dump(exclude_none=True)
            if profile_dict:
                existing_info = "\n".join([f"- {k}: {v}" for k, v in profile_dict.items()])
                messages.append(SystemMessage(content=f"The user has already provided some profile information:\n{existing_info}\nDo not ask for these details again unless they explicitly want to change them."))
                
        messages.append(HumanMessage(content=user_input))
        while True:
            response = self.llm_with_tools.invoke(messages)
            messages.append(response)
            
            if not getattr(response, "tool_calls", None):
                # If the LLM responds with plain text instead of a tool call
                messages.append(HumanMessage(content="Please use the tools to either ask for clarification or submit the UserRequirements."))
                continue

            for tool_call in response.tool_calls:
                if tool_call["name"] == "confirm_requirements":
                    user_response = confirm_requirements.invoke(tool_call["args"])
                    messages.append(ToolMessage(content=user_response, tool_call_id=tool_call["id"]))
                elif tool_call["name"] == "UserRequirements":
                    profile = UserRequirements(**tool_call["args"])
                    return profile, messages

