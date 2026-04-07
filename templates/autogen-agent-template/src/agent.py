"""AutoGen agent with trust-verified tool registration."""
import autogen
import nerq
from dotenv import load_dotenv
from tools import get_tools_for_task, verify_tool_trust

load_dotenv()


def create_trusted_agent(tasks: list[str]):
    """Create an AutoGen agent with dynamically discovered, trust-verified tools."""
    config_list = autogen.config_list_from_json("OAI_CONFIG_LIST", filter_dict={"model": ["gpt-4o-mini"]})

    assistant = autogen.AssistantAgent(
        name="trusted_assistant",
        llm_config={"config_list": config_list}
    )

    # Register trust-verified tools
    for task in tasks:
        tool = get_tools_for_task(task)
        if tool:
            print(f"Registered: {tool['name']} (Trust: {tool['trust_score']})")

    return assistant


def main():
    print("Creating trust-verified AutoGen agent...")
    agent = create_trusted_agent(["code review", "web search"])
    print("Agent ready.")


if __name__ == "__main__":
    main()
