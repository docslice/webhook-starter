"""Offline check: a real server on a free port, the DocSlice API replaced. Run: python -m unittest"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import receiver

SECRET = "s3cret-path-0123456789"


class TestReceiver(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), receiver.make_handler(SECRET, str(tmp / "events.db")))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        while not receiver.work.empty():           # each test starts with an empty, fully "done" queue
            receiver.work.get_nowait()
            receiver.work.task_done()

    def post(self, path, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_only_the_secret_path_and_known_events_are_accepted(self):
        event = {"event": "document.completed", "job_id": "job-1"}
        self.assertEqual(self.post("/webhooks/wrong", event), 404)
        self.assertEqual(self.post(f"/webhooks/{SECRET}", b"not json"), 400)
        self.assertEqual(self.post(f"/webhooks/{SECRET}", {"event": "other", "job_id": "x"}), 400)
        self.assertEqual(self.post(f"/webhooks/{SECRET}", {"event": "document.completed", "job_id": "../x"}), 400)
        self.assertEqual(self.post(f"/webhooks/{SECRET}", event), 204)
        self.assertEqual(self.post(f"/webhooks/{SECRET}", event), 204)       # duplicate: still 204...
        self.assertEqual(receiver.work.qsize(), 1)                            # ...but queued once

    def test_the_result_saved_is_the_one_read_from_the_api(self):
        api_job = {"id": "job-9", "status": "completed", "pages_count": 2, "data": {"total": 10}}
        with tempfile.TemporaryDirectory() as out, patch.object(receiver, "RESULTS", Path(out)), \
                patch.object(receiver, "fetch_job", return_value=api_job) as fetch:
            threading.Thread(target=receiver.worker, args=("key",), daemon=True).start()
            self.post(f"/webhooks/{SECRET}", {"event": "document.completed", "job_id": "job-9", "data": {"total": 999}})
            receiver.work.join()
            fetch.assert_called_once_with("job-9", "key")
            self.assertEqual(json.loads((Path(out) / "job-9.json").read_text())["data"], {"total": 10})


if __name__ == "__main__":
    unittest.main()
