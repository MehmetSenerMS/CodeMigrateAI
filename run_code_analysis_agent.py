from pathlib import Path
from tkinter import Tk, simpledialog

from crewai import Crew, Task, Process

from codemigrate.llm.crewai_llm import CodeMigrateLLM
from codemigrate.settings import get_api_url
from codemigrate.memory.memory_config import create_agent_memory
from codemigrate.agents.code_analysis_agent import (
    create_code_analysis_agent
)


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

API_URL = get_api_url()

SOURCE_FILE = PROJECT_ROOT / "legacy" / "CustomerService.cs"

MEMORY_SCOPE = "/project/codemigrate/code_analysis"


# ============================================================
# API Authentication
# ============================================================

window = Tk()
window.withdraw()

try:
    API_KEY = simpledialog.askstring(
        "CodeMigrate AI",
        "Enter your Colab API key:",
        show="*",
        parent=window
    )
finally:
    window.destroy()

if not API_KEY:
    raise ValueError("API key is required")


# ============================================================
# Initialize Remote LLM
# ============================================================

llm = CodeMigrateLLM(
    base_url=API_URL,
    api_key=API_KEY,
    max_new_tokens=512
)

print("Remote LLM:", llm.base_url)


# ============================================================
# Initialize Persistent Memory
# ============================================================

memory = create_agent_memory(
    project_root=PROJECT_ROOT,
    llm=llm
)


# ============================================================
# Retrieve Migration Policy
# ============================================================

migration_policy = (
    "CodeMigrate AI migration policy: preserve public "
    "class names, method names, return types and observable "
    "business behavior unless an explicit migration "
    "instruction requires a change."
)

existing_memories = memory.recall(
    "CodeMigrate AI migration policy preserve public methods",
    scope=MEMORY_SCOPE,
    limit=5,
    depth="shallow"
)

verified_policies = list(dict.fromkeys(
    item.record.content
    for item in existing_memories
    if item.record.content.startswith(
        "CodeMigrate AI migration policy:"
    )
))

# Do not save the same policy on every execution.
if migration_policy not in verified_policies:

    memory.remember(
        migration_policy,
        scope=MEMORY_SCOPE,
        categories=["migration_policy"],
        importance=0.9,
        source="project_rule"
    )

    verified_policies.append(migration_policy)

memory_context = "\n".join(
    f"- {policy}"
    for policy in verified_policies
)


# ============================================================
# Read Legacy Source
# ============================================================

if not SOURCE_FILE.is_file():
    raise FileNotFoundError(SOURCE_FILE)

source_code = SOURCE_FILE.read_text(
    encoding="utf-8"
)


# ============================================================
# Create Agent
# ============================================================

agent = create_code_analysis_agent(
    llm=llm
)


# ============================================================
# Create Analysis Task
# ============================================================

task = Task(
    description=f"""
Analyze the following C# source code.

PROJECT MIGRATION RULES:
{memory_context}

SOURCE CODE:
{source_code}

Identify:

1. Class names and their responsibilities.
2. Public methods and their exact signatures.
3. Business logic implemented by each method.
4. External dependencies.
5. Migration risks.
6. Behavior that must remain unchanged.

Important requirements:

- Analyze only the provided source code.
- Do not invent methods or dependencies.
- Do not rewrite the code.
- Do not propose calling other tools.
- Explain the actual behavior of each public method.
- Return a structured technical analysis.
""",

    expected_output=(
        "A technical C# analysis containing the sections: "
        "Classes, Public Methods, Business Logic, "
        "External Dependencies, Migration Risks, "
        "and Behavior to Preserve."
    ),

    agent=agent
)


# ============================================================
# Execute CrewAI
# ============================================================

crew = Crew(
    agents=[agent],
    tasks=[task],
    process=Process.sequential,

    # We manage memory explicitly in this stage.
    memory=False,

    verbose=True
)

print("\nStarting Code Analysis Agent...")

result = crew.kickoff()

analysis = result.raw.strip()


# ============================================================
# Validate Analysis
# ============================================================

expected_identifiers = [
    "CustomerService",
    "GetCustomerName",
    "IsCustomerActive"
]

missing_identifiers = [
    identifier
    for identifier in expected_identifiers
    if identifier not in analysis
]

if missing_identifiers:
    raise RuntimeError(
        "Agent analysis is incomplete. "
        f"Missing identifiers: {missing_identifiers}"
    )

if "next tool to be called" in analysis.lower():
    raise RuntimeError(
        "Agent generated tool-calling instructions "
        "instead of a code analysis."
    )


# ============================================================
# Save Validated Analysis to Memory
# ============================================================

memory.remember(
    (
        f"Code analysis for {SOURCE_FILE.name}:\n"
        f"{analysis}"
    ),
    scope=MEMORY_SCOPE,
    categories=["code_analysis"],
    importance=0.75,
    source="code_analysis_agent"
)


# ============================================================
# Results
# ============================================================

print("\n" + "=" * 60)
print("CODEMIGRATE AI - CODE ANALYSIS")
print("=" * 60)

print(analysis)

print("\n" + "=" * 60)
print("AGENT MEMORY")
print("=" * 60)

memories = memory.recall(
    "CustomerService business logic",
    scope=MEMORY_SCOPE,
    limit=3,
    depth="shallow"
)

for item in memories:
    print(
        f"Score: {item.score:.4f} | "
        f"Memory: {item.record.content[:250]}"
    )
print("\nCode Analysis Agent execution: PASS")
