"""A small, dependency-free receiver for DocSlice webhooks.

DocSlice calls your URL once when an asynchronous job ends (no retries, 10 s timeout) and the request is not signed.
So this receiver:
  1. listens on a secret path (/webhooks/<WEBHOOK_SECRET>) and answers 404 anywhere else;
  2. answers 204 at once and does the work in a background thread;
  3. ignores an event it has already seen (same job id), so a duplicate is harmless;
  4. never trusts the body: it reads the job again with GET /v1/jobs/{id} and your API key, and only then saves it.

    export DOCSLICE_API_KEY=ds_live_...  WEBHOOK_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
    python receiver.py                     # http://0.0.0.0:8000/webhooks/<secret>

Confirmed results land in results/<job id>.json. Replace handle_result() with your own logic.
"""
import json
import os
import queue
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API = os.environ.get("DOCSLICE_API_URL", "https://api.docslice.app")
EVENTS = {"document.completed", "document.failed", "batch.completed", "batch.failed"}
MAX_BODY = 5 * 1024 * 1024
RESULTS = Path(os.environ.get("RESULTS_DIR", "results"))
work: "queue.Queue[str]" = queue.Queue()


def seen_before(db_path: str, job_id: str) -> bool:
    """Records the job id; True if it was already there (the event is a duplicate)."""
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS events (job_id TEXT PRIMARY KEY)")
        return db.execute("INSERT OR IGNORE INTO events VALUES (?)", (job_id,)).rowcount == 0


def fetch_job(job_id: str, api_key: str) -> dict:
    request = urllib.request.Request(f"{API}/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def handle_result(job: dict) -> None:
    """Your logic goes here. The job comes from the API, not from the webhook body."""
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{job['id']}.json").write_text(json.dumps(job, indent=2, default=str), encoding="utf-8")
    print(f"job {job['id']}: {job['status']}, {job.get('pages_count', 0)} pages", flush=True)


def worker(api_key: str) -> None:
    while True:
        job_id = work.get()
        try:
            handle_result(fetch_job(job_id, api_key))
        except (urllib.error.URLError, ValueError, OSError) as exc:
            print(f"job {job_id}: could not confirm ({exc}); read it later with GET /v1/jobs/{job_id}", file=sys.stderr)
        finally:
            work.task_done()


def make_handler(secret: str, db_path: str):
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != f"/webhooks/{secret}":
                return self.reply(404)
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BODY:
                return self.reply(413 if length else 400)
            try:
                event = json.loads(self.rfile.read(length))
                job_id = str(event.get("job_id") or event.get("batch_id") or "")
            except (ValueError, AttributeError):
                return self.reply(400)
            if event.get("event") not in EVENTS or not job_id or len(job_id) > 100 or "/" in job_id:
                return self.reply(400)
            if not seen_before(db_path, job_id):
                work.put(job_id)
            self.reply(204)                       # 200, 201, 202 or 204 count as delivered

        def reply(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, fmt, *args):         # keep the secret path out of the logs
            sys.stderr.write(f"{self.command} {args[1] if len(args) > 1 else ''}\n")

    return Receiver


def main() -> None:
    api_key, secret = os.environ.get("DOCSLICE_API_KEY"), os.environ.get("WEBHOOK_SECRET", "")
    if not api_key or len(secret) < 16:
        sys.exit("Set DOCSLICE_API_KEY and a WEBHOOK_SECRET of at least 16 random characters (see README).")
    threading.Thread(target=worker, args=(api_key,), daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Listening on :{port}, path /webhooks/<WEBHOOK_SECRET>", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(secret, os.environ.get("EVENTS_DB", "events.db"))).serve_forever()


if __name__ == "__main__":
    main()
