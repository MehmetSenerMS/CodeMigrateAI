# Publishing CodeMigrate AI to GitHub

This guide assumes a Windows PowerShell session and a local project at
`C:\CodeMigrateAI`. GitHub account: `MehmetSenerMS`.

## 1. Install the documentation files

Copy the new `README.md`, `.gitignore`, `.gitattributes`, and
`preflight_github.py` to the **project root**. Your existing `README.md`
will be replaced, so keep a backup if it contains information you need.

**Do not overwrite `.env` or `.env.example`.** Inspect `.env.example` to
ensure it contains placeholder values only.

## 2. Inspect the local project before publishing

```powershell
Set-Location C:\CodeMigrateAI
git --version
git status
```

If Git reports that the directory is not a repository, initialize it:

```powershell
git init -b main
```

If Git reports an existing repository, do **not** reinitialize it, and inspect
`git remote -v` to avoid replacing an existing remote.

Check the ignore rules before staging:

```powershell
git check-ignore -v .env
git check-ignore -v models\example.safetensors
git check-ignore -v outputs\example.json
```

Each command should print the applicable ignore rule. `.env.example` should
remain publishable after confirming it has no credentials.

## 3. Prepare notebooks and sources

- Open each Colab `.ipynb` before including it. Remove saved execution outputs
  that reveal API keys, private source data, tunnel URLs, or machine-specific
  paths. Leave the training and evaluation code visible.
- Exclude model weights and the downloaded base model. Document the upstream
  base model and expected local adapter location instead.
- Review the licenses and attribution requirements of any third-party code or
  datasets. Do not add a repository-wide software license until you have
  chosen one and checked ownership/redistribution rights.
- Test your local environment independently. A GitHub README alone does not
  guarantee a reproducible installation.

## 4. Stage locally and run a publication check

```powershell
git add .
& "C:\Users\msmes\anaconda3\envs\codemigrate-ai\python.exe" preflight_github.py
git status --short
git diff --cached --stat
```

The preflight script scans **the staged Git index**, flags excluded paths,
oversized files, obvious secret patterns, and notebook outputs. It prints
file names and issue categories without printing secret values.

If it reports `FAIL`, inspect and fix the named files before committing.
Re-run `git add` for corrected files and repeat the preflight check. Do not
commit or push until it reports `PASS` and you have manually reviewed the
staged file names.

> The scanner is a precaution, not a guarantee that the repository is free of
> sensitive information. If a secret was already committed locally, ignoring
> it later does not remove it from Git history. Rotate exposed keys as needed.

## 5. Create an empty GitHub repository

Open [https://github.com/new](https://github.com/new) while signed in.

1. **Owner:** `MehmetSenerMS`.
2. **Repository name:** `CodeMigrateAI`.
3. **Description:** `QLoRA fine-tuned C# modernization assistant with hybrid RAG, CrewAI agents, RAGAS, and executable .NET validation.`
4. **Visibility:** start **Private** until the source and notebook audit is
   finished; change to **Public** later if you want a portfolio repository.
5. Leave *Add README*, *.gitignore*, and *License* unchecked (they already
   exist locally or are pending a licensing decision).
6. Create the repository.

## 6. Commit and push after review

```powershell
git commit -m "Add CodeMigrate AI source and evaluation documentation"
git remote -v
```

If no `origin` remote is configured, add:

```powershell
git remote add origin https://github.com/MehmetSenerMS/CodeMigrateAI.git
```

Then push:

```powershell
git branch -M main
git push -u origin main
```

If GitHub authentication is required, use Git Credential Manager, GitHub
Desktop, or `gh auth login` rather than adding a personal access token to the
remote URL or a tracked file.

**Do not run the push commands until the secret/privacy audit is complete.**

## 7. After the first push

- Verify the rendered Mermaid diagrams, tables, math equations, and badges.
- Add a screenshot of a *redacted* local run if you want a visual demo.
- Add a tested local dependency manifest and a separate Colab training
  environment manifest; Windows and CUDA environments need different packages.
- Choose and add a license after reviewing bundled third-party code.
- Make the repository public only when you are comfortable publishing the
  full source history.
