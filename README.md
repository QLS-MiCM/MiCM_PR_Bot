# MiCM_PR_Bot

Central GitHub Actions automation for the [QLS-MiCM](https://github.com/QLS-MiCM) organization.

## Workflows

| File | Purpose |
|------|---------|
| `reusable_pr_check_issue_deploy.yml` | Reusable workflow: posts a PR checklist comment and creates a tracking issue in `Workshop_Template` |
| `distribute_pr_check_workflow.yml` | Commits the thin caller workflow directly to each org repo's default branch when the canonical template changes |
| `workflow-templates/pr_check_issue_deploy_caller.yml` | Canonical caller text (not executed; read by the distributor) |
| `reusable_lint_workshop.yml` | Reusable workflow: lints the files a pull request changes in a workshop repo |
| `workflow-templates/lint_workshop_caller.yml` | Caller text for the lint workflow (not executed, not distributed automatically) |
| `scripts/lint_workshop.py` | The linter run by `reusable_lint_workshop.yml` |


## Updating workflows

- **Checklist / issue logic:** Edit `reusable_pr_check_issue_deploy.yml` only. All org repos pick up changes on the next PR open (no redistribution).
- **Caller trigger or guard:** Edit `workflow-templates/pr_check_issue_deploy_caller.yml` and merge to `main`. The distributor commits directly to each org repo's default branch.
- **Lint checks:** Edit `scripts/lint_workshop.py` or `reusable_lint_workshop.yml`. Repos that have the lint caller pick up changes on their next pull request.

## Workshop lint

The lint workflow checks the files a pull request changes.

It fails the check when a file cannot be opened or run at all:

- `.ipynb` is not valid JSON
- `.py`, `.R` or `.sh` does not parse
- `.Rmd` / `.qmd` has a broken YAML header or a code chunk that is never closed
- `.mlx` is not a valid archive

It only warns (annotations and a job summary) when:

- a notebook code cell or an Rmd/qmd chunk does not parse (student versions contain intentional blanks)
- a notebook was committed with an error output
- a notebook uses a relative image path, which does not render in Colab

To enable it in a repo, copy `workflow-templates/lint_workshop_caller.yml` to `.github/workflows/lint_workshop.yml` in that repo. The distributor does not push this caller.

Unlike the checklist workflow, the lint workflow runs on `pull_request`, with a read-only token and no secrets, so it can check out the pull request. The linter itself is always taken from this repo.

To run the linter locally:

```
pip install nbformat pyyaml
python scripts/lint_workshop.py path/to/file.ipynb     # given files
python scripts/lint_workshop.py --all                  # every tracked file in the current repo
```

## Reusable workflow access

MiCM_PR_Bot must allow reusable workflow access from repositories in the QLS-MiCM organization (Settings → Actions → General → Access).
