import tkinter as tk
from tkinter import simpledialog
from codemigrate.llm.remote_client import RemoteMigrationClient


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

API_URL = (
    "https://aimed-keep-justice-organisations.trycloudflare.com"
)


root = tk.Tk()
root.withdraw()

try:
    API_KEY = simpledialog.askstring(
        "CodeMigrate AI",
        "Enter your API key:",
        show="*",
        parent=root
    )
finally:
    root.destroy()

if not API_KEY:
    raise ValueError("API key is required")

# ------------------------------------------------------------
# Initialize Client
# ------------------------------------------------------------

client = RemoteMigrationClient(
    base_url=API_URL,
    api_key=API_KEY
)


try:

    # --------------------------------------------------------
    # Health Check
    # --------------------------------------------------------

    print("=" * 60)
    print("REMOTE MODEL HEALTH")
    print("=" * 60)

    health = client.health()

    print("Status:", health["status"])
    print("Model:", health["base_model"])
    print("Adapter:", health["adapter"])
    print("Device:", health["device"])

    assert health["status"] == "ready"

    # --------------------------------------------------------
    # Migration Request
    # --------------------------------------------------------

    instruction = (
        "Migrate legacy .NET Framework configuration code "
        "to modern .NET using IConfiguration and constructor "
        "injection. Preserve the class name, method name, "
        "return type and default value."
    )

    legacy_code = """
using System.Configuration;

public class NotificationSettings
{
    public string GetSenderName()
    {
        return ConfigurationManager.AppSettings["SenderName"]
            ?? "CodeMigrate";
    }
}
"""

    # --------------------------------------------------------
    # Remote Inference
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("GENERATING MODERN C# CODE")
    print("=" * 60)

    result = client.migrate(
        instruction=instruction,
        legacy_code=legacy_code
    )

    print("\n--- Generated Code ---\n")

    print(result["generated_code"])

    print("\n--- Inference Statistics ---")

    print(
        "Generation time:",
        result["generation_time"],
        "seconds"
    )

    print(
        "Generated tokens:",
        result["generated_tokens"]
    )

    # --------------------------------------------------------
    # Basic Checks
    # --------------------------------------------------------

    generated_code = result["generated_code"]

    assert "IConfiguration" in generated_code
    assert "NotificationSettings" in generated_code
    assert "GetSenderName" in generated_code

    print("\nRemote LLM inference: PASS")

finally:

    client.close()