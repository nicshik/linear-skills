# Security Policy

## Supported Versions

The `main` branch is the supported version.

## Reporting A Vulnerability

If you find a vulnerability, open a private report through GitHub's security advisory flow if available, or contact the repository owner directly.

Do not open a public issue containing:

- Linear API keys;
- workspace tokens;
- private issue data;
- command logs with secrets.

## API Key Handling

These skills require a Linear personal API key. Store it outside the repository:

```bash
export LINEAR_API_KEY=<linear-api-key>
```

or in a local ignored env file:

```text
LINEAR_API_KEY=<linear-api-key>
```

If a key is exposed in chat, logs, or git history, revoke it in Linear and create a new one.

## Permission Scope

For Codex, approve only the script entrypoints:

```text
python3 linear-change-status/scripts/change_status.py
python3 linear-comment-issue/scripts/comment_issue.py
python3 linear-create-issue/scripts/create_issue.py
python3 linear-custom-view/scripts/custom_view.py
python3 linear-custom-view-setup/scripts/custom_view_setup.py
python3 linear-custom-view-update/scripts/custom_view_update.py
python3 linear-label-setup/scripts/label_setup.py
python3 linear-list-issues/scripts/list_issues.py
python3 linear-read-issue/scripts/read_issue.py
python3 linear-relation-setup/scripts/relation_setup.py
python3 linear-update-issue/scripts/update_issue.py
```

Do not approve broad command prefixes such as `python3`.
