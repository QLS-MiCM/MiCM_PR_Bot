# MiCM_PR_Bot

Central GitHub Actions automation for the [QLS-MiCM](https://github.com/QLS-MiCM) organization.

## Workflows

| File | Purpose |
|------|---------|
| `reusable_pr_check_issue_deploy.yml` | Reusable workflow: posts a PR checklist comment and creates a tracking issue in `Workshop_Template` |
| `distribute_pr_check_workflow.yml` | Syncs the thin caller workflow to all org repos when the canonical template changes |
| `workflow-templates/pr_check_issue_deploy_caller.yml` | Canonical caller text (not executed; read by the distributor) |

## Secrets

| Secret | Scope | Purpose |
|--------|-------|---------|
| `GH_ORG_SYNC_TOKEN` | MiCM_PR_Bot repo | PAT or GitHub App token for org-wide caller distribution |
| `WORKSHOP_TEMPLATE_TOKEN` | Org secret | Creates tracking issues in `Workshop_Template` |

## Updating workflows

- **Checklist / issue logic:** Edit `reusable_pr_check_issue_deploy.yml` only. All org repos pick up changes on the next PR open (no redistribution).
- **Caller trigger or guard:** Edit `workflow-templates/pr_check_issue_deploy_caller.yml` and merge to `main`. The distributor opens PRs across org repos.

## Reusable workflow access

MiCM_PR_Bot must allow reusable workflow access from repositories in the QLS-MiCM organization (Settings → Actions → General → Access).
