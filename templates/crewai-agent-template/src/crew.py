"""CrewAI crew with trust-verified agents."""
from crewai import Agent, Task, Crew
import nerq
from dotenv import load_dotenv
from tools import get_tools_for_task

load_dotenv()


def create_trusted_crew(tasks_needed: list[str]):
    """Build a crew with trust-verified tools for each task."""
    agents = []
    for task_desc in tasks_needed:
        tool = get_tools_for_task(task_desc)
        if tool:
            agent = Agent(
                role=task_desc,
                goal=f"Execute {task_desc} using trusted tools",
                backstory=f"Specialist in {task_desc}. Uses {tool.get('name')} (Trust: {tool.get('trust_score')}).",
                tools=[]
            )
            agents.append(agent)
    return agents


def main():
    print("Building trusted crew...")
    agents = create_trusted_crew(["code review", "web search", "data analysis"])
    print(f"Crew ready with {len(agents)} trust-verified agents.")

    tasks = [
        Task(description="Review the codebase", agent=agents[0], expected_output="Code review report")
    ] if agents else []

    if agents and tasks:
        crew = Crew(agents=agents, tasks=tasks)
        print("Crew assembled. Ready to run.")


if __name__ == "__main__":
    main()
