# Additional Information for Nonprofit Fork of Django-Ledger

To manage synchronization with the original Django-Ledger, we are using the following branching structure.

## 🔥 Branching Model Overview

This repository uses a **structured branching model** to support clean development, safe integration, and team collaboration.

| Branch               | Purpose                                                               |
|----------------------|-----------------------------------------------------------------------|
| `master`             | Matches the original Django-Ledger                                    |
| `refactor`           | Safe refactorings without behavior changes                            |
| `features`           | Persistent branch with tested refactor + features, shared across team |


```text
(master)
    |
    +--- (refactor)
             |
             +--> Developers pull from refactor and branch (locally) for new refactoring & cleanup
             |
             +--- (features)
                       |
                       +--> Developers pull from features and branch (locally) for new features
```

With this model, we can control when we pull from the original Django-Ledger (in `master`). We can have refactoring & cleanup in `refactor`, separate from new features in `features`. 
This lets us submit cleaner pull requests to the original Django-Ledger with just refactoring (from `refactor`) or refactoring + features (from `features`).

---

## 🚀 Workflow
Whether you are working off of `refactor` or `features`, follow the best practice of doing integration testing locally with your code before pushing or submitting a PR back to the parent branch. It will be easier if you create local `refactor` and `features` branches that mirror the structure in GitHub.

For example, when developing a new feature:
- Update your local `features` branch to match GitHub.
- Branch from `features` to create your feature branch.
- Test and check-in on your feature branch.
- Merge the feature branch back to `features`
- Push `features` back to GitHub (or submit a PR)

## 📢 Notes for Contributors

- Update your local branches regularly:

```bash
git fetch origin
git checkout features
git pull origin features
```

- Before starting a new feature branch, **always branch off the latest `features`** unless instructed otherwise.
