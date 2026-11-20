from crewai import Agent


def create_code_analysis_agent(llm):

    agent = Agent(
        role="Legacy Code Analysis Specialist",

        goal=(
            "Accurately analyze legacy C# code, identify its "
            "business behavior, dependencies and migration risks."
        ),

        backstory=(
            "You are a senior .NET engineer experienced in "
            "analyzing enterprise C# applications. "
            "You carefully inspect source code and preserve "
            "existing business behavior during migrations."
        ),

        llm=llm,

        # Memory will be managed explicitly.
        memory=False,

        # No automatic tool calls for this agent.
        tools=[],

        allow_delegation=False,

        max_iter=2,

        max_execution_time=240,

        verbose=True
    )

    return agent