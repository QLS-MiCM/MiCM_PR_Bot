# MiCM_PR_Bot

Central GitHub Actions automation for the [QLS-MiCM](https://github.com/QLS-MiCM) organization.

## Workflows

| File | Purpose |
|------|---------|
| `reusable_pr_check_issue_deploy.yml` | Reusable workflow: posts a PR checklist comment and creates a tracking issue in `Workshop_Template` |
| `distribute_pr_check_workflow.yml` | Commits the thin caller workflow directly to each org repo's default branch when the canonical template changes |
| `workflow-templates/pr_check_issue_deploy_caller.yml` | Canonical caller text (not executed; read by the distributor) |


## Updating workflows

- **Checklist / issue logic:** Edit `reusable_pr_check_issue_deploy.yml` only. All org repos pick up changes on the next PR open (no redistribution).
- **Caller trigger or guard:** Edit `workflow-templates/pr_check_issue_deploy_caller.yml` and merge to `main`. The distributor commits directly to each org repo's default branch.

## Reusable workflow access

MiCM_PR_Bot must allow reusable workflow access from repositories in the QLS-MiCM organization (Settings → Actions → General → Access).
