This script is intended to be used as a git submodule or simply copied to other repositories. It converts program output (currently python type checkers) into GitHub annotation so that they can be displayed properly while running CI/CD workflows.

Some checkers and linters do support CI/CD services out-of-box so no data conversion is necesssary (like `pyrefly` or `ty`), but not all have some level of support. Those neglecting CI/CD demands (like `mypy`) would find lightweight conversion scripts useful. In some cases, third party GitHub actions are available, but not all of them are well maintained, or some of them could be risky (like `reviewdog` requiring high privileged secret tokens).

## Supported services

| Checker or Linter (as input) | CI/CD service (as output) |
| --- | --- |
| `mypy` | `GitHub text format` |
| `pyright` | `GitHub JSON annotation` |
| `pyrefly` | `GitLab Code Quality JSON` |
| `basedpyright` | |
| `ty` | |

