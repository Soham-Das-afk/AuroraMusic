# Contributing to AuroraMusic

Thanks for your interest in improving AuroraMusic! I accept small fixes and improvements.

## Ground rules

- Be respectful and constructive.
- Keep public logs/tokens out of issues and PRs. Use redactions.
- Follow the source-available license and keep NOTICE/credits intact.

## How to propose changes

1. Open an issue describing the problem or enhancement.
2. Fork the repo and create a feature branch from `master`.
3. Make minimal, focused changes; add brief tests where practical.
4. Run the bot locally to validate (see README quick start).
5. Open a pull request linking the issue; describe the changes and risks.

## Code style and checks

- Python 3.11
- Keep logging structured; avoid `print()` (use `logging`)
- Prefer small, composable functions and clear error handling
- Pin or document dependency updates in `requirements.txt`

## Running locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# fill .env with BOT_TOKEN and ALLOWED_GUILD_IDS
python src/bot.py
```

## Commit and PR guidelines

- Keep commits atomic with meaningful messages (e.g., `fix:`, `feat:`, `docs:`, `ci:`)
- Update README/docs when behavior changes
- Reference issues with `Fixes #123` when appropriate

## Security

See `SECURITY.md` for how to report vulnerabilities. Do not include exploit details in public threads.
