"""Main agent with dynamic tool discovery."""
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from tools import get_tools_for_task

load_dotenv()


def main():
    llm = ChatOpenAI(model="gpt-4o-mini")

    # Dynamic tool discovery — finds best tools via Nerq
    print("Discovering tools...")
    code_tool = get_tools_for_task("code review")
    search_tool = get_tools_for_task("web search")

    tools_found = sum(1 for t in [code_tool, search_tool] if t)
    print(f"Ready with {tools_found} trust-verified tools.")

    # Use the LLM directly for now
    response = llm.invoke("What can you help me with?")
    print(response.content)


if __name__ == "__main__":
    main()
