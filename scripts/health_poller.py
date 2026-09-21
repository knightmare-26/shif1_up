#!/usr/bin/env python3
"""
Health-check poller for local development.

Starts the backend (:8000) and frontend (:3000) if they aren't already
healthy, then polls their health endpoints and restarts whichever one stops
responding. Servers that were already running are adopted, never duplicated
or killed.

    python scripts/health_poller.py              # start + supervise
    python scripts/health_poller.py --check      # print status and exit
    python scripts/health_poller.py --only backend

Child output goes to logs/<service>.log. Stdlib only, so the system Python
is enough; the backend itself runs under venv/ when it exists.
"""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
NODE_DIRS = [r"C:\Program Files\nodejs", r"C:\Program Files (x86)\nodejs"]


def log(msg):
    print(f"{time.strftime('%H:%M:%S')}  {msg}", flush=True)


def load_env_file(path):
    """Minimal .env reader (the backend loads the same file via python-dotenv).
    Existing environment variables win, matching dotenv's default."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def find_python():
    for rel in ("venv/Scripts/python.exe", "venv/bin/python"):
        if (ROOT / rel).exists():
            return str(ROOT / rel)
    return sys.executable


def find_npm():
    """Return (npm path, extra PATH dir) — npm isn't always on PATH on Windows."""
    found = shutil.which("npm")
    if found:
        return found, None
    for d in NODE_DIRS:
        npm = Path(d) / "npm.cmd"
        if npm.exists():
            return str(npm), d
    return None, None


def probe(url):
    """(alive, body). Any HTTP answer below 500 means the server is up."""
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return True, r.read(65536)
    except urllib.error.HTTPError as exc:
        return exc.code < 500, b""
    except (urllib.error.URLError, OSError):
        return False, b""


def port_in_use(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def backend_problems(body):
    """Names of the /health checks that aren't 'ok' (empty when healthy)."""
    try:
        checks = json.loads(body).get("checks", {})
    except (ValueError, AttributeError):
        return []
    # A backend running against Supabase heals its own database connection (and
    # wakes a paused project), so those problems are labelled and never restarted.
    self_healing = bool(checks.get("database", {}).get("self_healing"))
    problems = []
    for name, c in checks.items():
        if c.get("status") == "ok":
            continue
        label = f"{name}: {c.get('status')}"
        if self_healing and name in ("duckdb", "database"):
            label += " (self-healing)"
        problems.append(label)
    return problems


SUPABASE_API = "https://api.supabase.com/v1/projects"
WAKING = {"INACTIVE", "COMING_UP", "RESTORING", "RESTARTING", "UPGRADING"}


def supabase_ref():
    """Project ref from SUPABASE_PROJECT_REF, else parsed out of DATABASE_URL."""
    ref = os.environ.get("SUPABASE_PROJECT_REF")
    if ref:
        return ref
    url = urllib.parse.urlsplit(os.environ.get("DATABASE_URL", ""))
    if url.username and url.username.startswith("postgres."):  # pooler login: postgres.<ref>
        return url.username.split(".", 1)[1]
    host = url.hostname or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):  # direct: db.<ref>.supabase.co
        return host[len("db."):-len(".supabase.co")]
    return None


class SupabaseWatcher:
    """Restores a paused Supabase project through the Management API.

    Free-tier projects pause after a week idle, which shows up as the pooler
    answering "tenant/user not found". Needs SUPABASE_ACCESS_TOKEN
    (dashboard > Account > Access Tokens); without one it only explains what to do.
    """

    def __init__(self):
        self.ref = supabase_ref()
        self.token = os.environ.get("SUPABASE_ACCESS_TOKEN")
        self.state = None
        self.next_check = 0.0
        self.restore_at = 0.0
        self.waking = False

    @property
    def can_restore(self):
        return bool(self.ref and self.token)

    def report(self, state):
        if state != self.state:
            self.state = state
            log(f"supabase: {state}")

    def call(self, method, suffix=""):
        req = urllib.request.Request(
            f"{SUPABASE_API}/{self.ref}{suffix}", method=method,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except (urllib.error.URLError, OSError, ValueError):
            return 0, {}

    def tick(self, now):
        """Check the project; True on the tick it comes back up after being asleep."""
        if not self.can_restore:
            where = f"https://supabase.com/dashboard/project/{self.ref}" if self.ref else "the Supabase dashboard"
            self.report(f"F1 database unreachable. If the project is paused, restore it at {where}, "
                        "or set SUPABASE_ACCESS_TOKEN and I'll do it")
            return False
        if now < self.next_check:
            return False
        self.next_check = now + 15
        code, data = self.call("GET")
        if code in (401, 403):
            self.next_check = now + 300
            self.report(f"access token rejected (HTTP {code})")
            return False
        if code != 200:
            self.report(f"Management API not reachable (HTTP {code})")
            return False
        status = data.get("status")
        if status == "INACTIVE" and now - self.restore_at > 600:
            self.restore_at = now
            code, _ = self.call("POST", "/restore")
            log(f"supabase: project is paused - restore requested (HTTP {code})")
        if status in WAKING:
            self.waking = True
            self.report(f"waking up ({status})")
            return False
        came_back = self.waking and status == "ACTIVE_HEALTHY"
        self.waking = False
        self.report("active" if status == "ACTIVE_HEALTHY" else str(status))
        return came_back


class Service:
    def __init__(self, name, cmd, env, url, port, grace, max_fails, check_problems=None):
        self.name, self.cmd, self.env = name, cmd, env
        self.url, self.port = url, port
        self.grace, self.max_fails = grace, max_fails
        self.check_problems = check_problems
        self.proc = None
        self.started_at = 0.0
        self.next_start = 0.0
        self.backoff = 2
        self.fails = 0
        self.state = None
        self.problems = []
        self.hold = False  # set while an outside dependency (Supabase) is waking up
        self.degraded_ticks = 0
        self.degraded_restarts = 0
        self.degraded_next = 0.0

    def restart(self, now):
        self.stop()
        self.start(now, force=True)
        self.degraded_ticks = 0

    def report(self, state):
        if state != self.state:
            self.state = state
            log(f"{self.name}: {state}")

    def start(self, now, force=False):
        if not force and now < self.next_start:
            return
        LOG_DIR.mkdir(exist_ok=True)
        flags = {}
        if os.name == "nt":
            flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            flags["start_new_session"] = True
        with open(LOG_DIR / f"{self.name}.log", "ab") as out:
            self.proc = subprocess.Popen(
                self.cmd, cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=subprocess.STDOUT, **flags,
            )
        self.started_at = now
        self.next_start = now + self.backoff
        self.backoff = min(self.backoff * 2, 60)
        self.fails = 0
        self.report("starting")

    def stop(self):
        if not self.proc:
            return
        if self.proc.poll() is None:
            if os.name == "nt":
                # /T: npm and uvicorn's reloader leave child processes holding the port
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def tick(self, now, restart_degraded_max):
        if self.proc and self.proc.poll() is not None:
            log(f"{self.name}: process exited with code {self.proc.returncode} (see logs/{self.name}.log)")
            self.proc = None

        alive, body = probe(self.url)
        self.problems = self.check_problems(body) if alive and self.check_problems else []
        if alive:
            self.fails = 0
            if not self.problems:
                self.backoff, self.degraded_ticks, self.degraded_restarts = 2, 0, 0
                return self.report("up")
            self.report("degraded (" + ", ".join(self.problems) + ")")
            self.degraded_ticks += 1
            # Startup connections are made once, so a failure sticks until the next
            # restart. Retry quickly a few times, then every 5 minutes.
            self_healing = all("self-healing" in p for p in self.problems)
            if self.proc and not self.hold and not self_healing and restart_degraded_max > 0 \
                    and self.degraded_ticks >= 2 and now >= self.degraded_next:
                self.degraded_restarts += 1
                fast = self.degraded_restarts <= restart_degraded_max
                self.degraded_next = now + (60 if fast else 300)
                if self.degraded_restarts == restart_degraded_max + 1:
                    log(f"{self.name}: still degraded after {restart_degraded_max} restarts — retrying every 5 min")
                log(f"{self.name}: restarting to retry (attempt {self.degraded_restarts})")
                self.restart(now)
            return

        if self.proc is None:
            if port_in_use(self.port):
                return self.report(f"unhealthy, but port {self.port} is held by a process I didn't start")
            self.report("down")
            return self.start(now)

        if now - self.started_at < self.grace:
            return
        self.fails += 1
        if self.fails >= self.max_fails:
            log(f"{self.name}: no healthy response for {self.fails} checks — restarting")
            self.report("down")
            self.restart(now)


def build_services():
    base = {**os.environ, "PYTHONUTF8": "1"}
    services = {
        "backend": Service(
            "backend", [find_python(), "-X", "utf8", "start_backend.py"], base,
            "http://127.0.0.1:8000/health", 8000, grace=60, max_fails=6,
            check_problems=backend_problems,
        ),
    }
    npm, node_dir = find_npm()
    if npm:
        env = {**base, "BROWSER": "none", "PORT": "3000"}
        if node_dir:
            env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
        services["frontend"] = Service(
            "frontend", [npm, "start"], env, "http://127.0.0.1:3000", 3000,
            grace=180, max_fails=6,
        )
    else:
        log("frontend: npm not found on PATH or in Program Files\\nodejs — skipping")
    return services


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["backend", "frontend"], help="supervise just one service")
    ap.add_argument("--interval", type=float, default=5, help="seconds between health checks (default 5)")
    ap.add_argument("--max-degraded-restarts", type=int, default=3,
                    help="quick restarts (60s apart) when the backend reports degraded, before "
                         "slowing to every 5 min; 0 disables (default 3)")
    ap.add_argument("--check", action="store_true", help="print current status and exit (non-zero if any service is down)")
    args = ap.parse_args()

    load_env_file(ROOT / ".env")
    services = build_services()
    if args.only:
        services = {k: v for k, v in services.items() if k == args.only}

    if args.check:
        down = False
        for s in services.values():
            alive, body = probe(s.url)
            problems = s.check_problems(body) if alive and s.check_problems else []
            status = "down" if not alive else ("degraded (" + ", ".join(problems) + ")" if problems else "up")
            down = down or not alive
            print(f"{s.name}: {status}")
        sys.exit(1 if down else 0)

    supabase = SupabaseWatcher()
    backend = services.get("backend")
    if backend and not os.environ.get("DATABASE_URL"):
        log("note: DATABASE_URL isn't set here, so the backend will use the local DuckDB file, which may be out of date")
    log(f"supervising {', '.join(services)} every {args.interval:g}s — Ctrl+C stops services started here")
    try:
        while True:
            now = time.time()
            if backend:
                backend.hold = supabase.can_restore and supabase.waking
            for s in services.values():
                s.tick(now, args.max_degraded_restarts)
            # "duckdb" is the /health key for the F1 data store (Supabase when DATABASE_URL is set)
            if backend and any(p.startswith("duckdb:") and "self-healing" not in p for p in backend.problems):
                if supabase.tick(now):
                    if backend.proc:
                        log("backend: Supabase is back — restarting to reconnect")
                        backend.restart(now)
                    else:
                        log("backend: Supabase is back — restart the backend to reconnect (not started by me)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log("stopping")
    finally:
        for s in services.values():
            s.stop()


if __name__ == "__main__":
    main()
