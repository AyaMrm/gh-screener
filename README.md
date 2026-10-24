# GitHub Profile Screener

A CLI tool that screens GitHub profiles against criteria chosen by the user
and returns only the profiles that match **all** selected criteria.

1. Give one or more GitHub usernames or profile links.
2. Choose filters (commits, preferred stack, open source projects).
3. Get the matching profiles. Invalid usernames are reported without
   blocking the others.

Data source: [GitHub API](https://docs.github.com/en).

## Installation

Requirements: Python 3.11 or newer and a GitHub token. A read-only token is
enough for the planned GitHub API operations.

Create a virtual environment and install the project with its development
dependencies:

```bash
python -m venv .venv
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

```bash
# Linux/macOS
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

Then add the token to `.env`:

```env
GITHUB_TOKEN=your_github_token
```

Never commit `.env` or any other file containing a real token.

## Development commands

The project currently contains the package scaffold. The commands below are
the checks configured for local development and CI:

```bash
# Check code style
ruff check .

# Run tests
pytest
```

The `gh-screener` console entry point is declared in `pyproject.toml`, but the
screening CLI is not implemented yet. The usage command will be added here
when `main.py` and `cli/commands.py` are implemented.

## Project structure

```text
src/gh_screener/
├── main.py          # assembles everything
├── cli/             # user input and output
├── application/     # the screening workflow
├── domain/          # models, filters, rules (no GitHub, no HTTP)
└── infra/           # GitHub API client
tests/
```

## The one rule

```text
cli -> application -> domain <- infra
```

- `domain` never imports the other layers.
- Only `infra` talks to GitHub.
- Only `cli` talks to the user.

## How we work

1. Create a branch: `<username>/feat/<IssueName>`.
2. Before pushing: `ruff check .` and `pytest` must pass.
3. Link your branch to the issue you worked on.
4. Open a pull request and explain what you changed.
5. Nobody pushes directly to `main`.
