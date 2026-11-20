# CodeMigrate AI — Shared Inference API Configuration

All Spyder runner scripts now obtain the inference API base URL from one place:

`C:\CodeMigrateAI\.env`

## 1. Copy the files

Extract the archive into `C:\CodeMigrateAI\` while preserving the
`codemigrate/settings.py` directory structure. Do not overwrite an existing
`.env` file or share it publicly.

The updated runners are:

- `run_code_analysis_agent.py`
- `run_documentation_agent.py`
- `run_code_migration_agent.py`
- `run_multi_agent_pipeline.py`

## 2. Create the local configuration file

In Windows PowerShell, run this only if `.env` does not already exist:

```powershell
Copy-Item C:\CodeMigrateAI\.env.example C:\CodeMigrateAI\.env
notepad C:\CodeMigrateAI\.env
```

Set `CODEMIGRATE_API_URL` to the currently active Cloudflare base URL:

```dotenv
CODEMIGRATE_API_URL=https://your-active-tunnel.trycloudflare.com
```

Do not append `/chat` or `/migrate`. Keep the existing interactive API key
prompt; the key does not need to be saved in `.env`.

## 3. Run as before

```python
%runfile C:/CodeMigrateAI/run_multi_agent_pipeline.py --wdir
```

Each runner calls `get_api_url()` when executed. If the public tunnel address
changes, edit only `.env`, then run the script again.

The `CODEMIGRATE_API_URL` process environment variable takes precedence over
`.env`. If changing `.env` appears ineffective, check whether Spyder or Windows
has that environment variable set already.

## Notes

- No additional pip packages are required for the shared URL configuration.
- The Quick Tunnel address itself is temporary. Centralizing it makes project
  configuration consistent; it does not create a permanent public hostname.
- A stable public hostname requires separate hosting or a named tunnel with a
  domain you control.
- Add `.env` to your project's `.gitignore` before pushing to GitHub.
- If other project files still hardcode an API URL, replace their assignment
  with `from codemigrate.settings import get_api_url` and
  `API_URL = get_api_url()`.
