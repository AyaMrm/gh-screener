# GitHub Profile Screener

A CLI tool that screens GitHub profiles against criteria chosen by the user
and returns only the profiles that match **all** selected criteria.

1. Give one or more GitHub usernames or profile links.
2. Choose filters (commits, preferred stack, public repositories).
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

The commands below are the checks configured for local development and CI:

```bash
# Check code style
ruff check .

# Run tests
pytest
```

The live GitHub API integration tests are marked `integration`. They are
skipped automatically when `GITHUB_TOKEN` is unavailable. To run only those
tests, configure the token in `.env` or the environment and run:

```bash
pytest -m integration
```

To run only the tests that do not contact GitHub:

```bash
pytest -m "not integration"
```

After installing the project, display the CLI help with:

```bash
gh-screener --help
```

Screen profiles with one or more criteria, for example:

```bash
gh-screener octocat torvalds --commit-contributions active
gh-screener https://github.com/octocat --languages Python --languages Go
gh-screener octocat --public-repositories senior-dev
```

If `GITHUB_TOKEN` is missing, the command displays a short configuration
message and exits without a traceback.

## Criteria options

All user-facing criteria options and their numeric thresholds are defined in
one place: `src/gh_screener/domain/criteria.py`. The application should use
`build_criteria()` instead of duplicating these values in the CLI or GitHub
client.

### GitHub-recognized commit contributions in the last 12 months

| Option | Requirement |
| --- | --- |
| `low` | fewer than 50 commit contributions |
| `active` | 50 or more commit contributions |
| `highly-active` | 200 or more commit contributions |
| `very-active` | 500 or more commit contributions |
| `legendary` | 2,000 or more commit contributions |

The `--commit-contributions` filter uses the count returned by GitHub's
contributions API over a rolling 365-day period. It follows GitHub's rules for
attributing contributions and may differ from a count of every raw Git commit.
For example, `active` matches profiles with at least 50 contributions, while
`legendary` matches profiles with at least 2,000. The options intentionally
overlap: a legendary profile also meets the very-active and active thresholds.

### Public repositories

| Option | Requirement |
| --- | --- |
| `senior-dev` | 20 or more public repositories |
| `github-ceo` | 50 or more public repositories |

Every public repository counts, including forks. A license declaration is not
required; private repositories are excluded.

### Languages

Languages are selected by name, for example `Python` or `Go`. They do not have
a numeric threshold. Multiple languages are normalized into a set and can be
passed together to `build_criteria()`.

If no criterion is selected, `build_criteria().is_empty` is `True`. An
unsupported option raises `UnknownCriteriaOptionError` with the available
options in the error message.

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
