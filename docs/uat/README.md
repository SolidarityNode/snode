# User acceptance testing (UAT)

Every pull request is tested by hand by the maintainer before it is merged. This page explains
how to get a clean, repeatable test environment. Each PR has its own checklist: the
**"How to test (UAT)"** section of the PR, and for larger changes a file in this folder
(for example [`00-bootstrap.md`](00-bootstrap.md)).

Everything runs on your own machine and listens on `127.0.0.1` only. The database contains
**synthetic data only** ([`data/synthetic/demo/`](../../data/synthetic/demo/README.md)).

## 1. One-time setup on a fresh machine (Windows with WSL2 and Podman)

1. Install WSL2 with Ubuntu (PowerShell as administrator: `wsl --install -d Ubuntu`), restart,
   and open the **Ubuntu** terminal. All commands below run there.
2. Install the tools:
   ```bash
   sudo apt update && sudo apt install -y git make podman podman-compose python3
   curl -LsSf https://astral.sh/uv/install.sh | sh          # uv (Python)
   curl -fsSL https://fnm.vercel.app/install | bash         # fnm (Node.js versions)
   ```
   Open a **new** terminal, then:
   ```bash
   fnm install 26 && fnm default 26
   curl -fsSL https://get.pnpm.io/install.sh | sh -          # pnpm
   ```
   Open a new terminal again so all tools are on `PATH`.
3. Get the code:
   ```bash
   git clone https://github.com/SolidarityNode/snode.git && cd snode
   ```
4. Check the tools and install dependencies: `make setup`. If a tool is missing, the message
   names it. `make setup` also creates `.env` from `.env.example`; you do not need to edit it.

Docker works too: prefix commands with `CONTAINER_ENGINE=docker COMPOSE="docker compose"`.

## 2. Testing a pull request

```bash
git fetch origin
git switch <branch-of-the-PR>      # shown at the top of the PR
git pull
make setup                          # dependencies may have changed
make uat
```

`make uat` asks you to type `yes` because it **deletes the local database** and starts from a
clean state. It then builds and starts everything, applies database migrations, loads the
synthetic demo dataset and prints the addresses to open:

| What | Address |
| --- | --- |
| Frontend (the application) | http://127.0.0.1:8080 |
| Frontend health page | http://127.0.0.1:8080/health |
| Backend API documentation | http://127.0.0.1:8000/docs |
| Backend health | http://127.0.0.1:8000/health |
| Backend version | http://127.0.0.1:8000/version |

**Which build am I testing?** The footer of every page shows the backend version, the git
commit and `APP_ENV`, plus the commit the frontend was built from. They must match the last
commit of the PR (`git rev-parse --short=12 HEAD`). A `-dirty` suffix means the code on your machine
has local changes.

Then follow the PR's "How to test (UAT)" steps.

## 3. Looking inside the database

```bash
make db-shell
```

opens `psql` in the database container. Useful commands:

| Command | Shows |
| --- | --- |
| `\dn` | schemas (`demo` holds the synthetic demo data) |
| `\dt demo.*` | demo tables |
| `SELECT * FROM demo.spatial_units;` | the 8 fictional spatial units |
| `\q` | quit |

The database is also reachable from desktop tools (for example QGIS or DBeaver) at
`127.0.0.1:5432`, with the user, password and database name from `.env`.

## 4. Logs and status

| Command | Use |
| --- | --- |
| `make ps` | are the containers running and `healthy`? |
| `make logs` | follow all logs (Ctrl+C to stop following) |
| `make wait` | wait until the backend is ready |
| `make check-config APP_ENV=production` | would the backend accept this configuration in production? |

## 5. Starting again

| Command | Effect |
| --- | --- |
| `make down` | stop everything; the database is kept |
| `make stop SERVICE=backend` | stop one service, keep the others running |
| `make up` | start again with the same database |
| `make seed` | reload the demo dataset (safe to repeat) |
| `make reset` | **delete the database**, start, migrate and seed (asks for `yes`; `FORCE=1` skips the question) |
| `make uat` | `reset`, then `up`, then print the addresses |

## 6. Reporting a problem

- **About a PR:** comment on the PR with the step number, what you expected, what you saw, a
  screenshot if useful, the build commit from the footer, and the relevant part of
  `make logs`. The maintainer adds the `uat-failed` label.
- **Anything else:** open a **Bug report** issue.
- Never paste real personal data, passwords or the contents of `.env` into issues or comments.
