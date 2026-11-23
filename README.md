# webhook-starter

A ready-to-use receiver for [DocSlice](https://docslice.app) webhooks: start a long conversion with `mode=async`, get a
call when it ends, and save the result. **Python standard library only**, one file, with a Dockerfile.

DocSlice makes **one** delivery attempt with a 10-second timeout and the request is **not signed**
([webhooks guide](https://docslice.app/docs/guides/webhooks/)). This receiver is built around that:

| Rule | What `receiver.py` does |
|---|---|
| Only you should be able to call it | It listens on a secret path, `/webhooks/<WEBHOOK_SECRET>`, and answers `404` anywhere else. It never logs the path. |
| Answer fast | It answers `204` at once and does the work in a background thread. |
| Be idempotent | It records each `job_id` (or `batch_id`) in SQLite and ignores a repeated event. |
| Do not trust the body | It reads the job again with `GET /v1/jobs/{id}` and your API key, and saves **that** answer. |

## Run it locally

```bash
git clone https://github.com/docslice/webhook-starter.git
cd webhook-starter
export DOCSLICE_API_KEY="ds_live_..."      # free key: https://api.docslice.app/app#signup
export WEBHOOK_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
python3 receiver.py                         # listens on :8000
```

DocSlice must reach your receiver from the internet, over HTTPS. To test from your machine, expose port 8000 with a
tunnel (for example `cloudflared tunnel --url http://localhost:8000` or `ngrok http 8000`), then start a job:

```bash
python3 submit.py path/to/invoice.pdf "https://<your-tunnel-host>/webhooks/$WEBHOOK_SECRET"
```

When the job ends the receiver prints a line and writes `results/<job id>.json`.

Simulate a delivery without DocSlice:

```bash
curl -i -X POST "http://localhost:8000/webhooks/$WEBHOOK_SECRET" \
  -H "Content-Type: application/json" -d '{"event":"document.completed","job_id":"<a real job id>"}'
```

## Deploy

Any host that runs a container or Python 3.9+ works:

```bash
docker build -t docslice-webhook .
docker run -d -p 8000:8000 -v docslice-data:/app/data \
  -e DOCSLICE_API_KEY=ds_live_... -e WEBHOOK_SECRET=... docslice-webhook
```

Put it behind your HTTPS reverse proxy, or on a platform that gives you HTTPS (Fly.io, Railway, Render, Cloud Run...).
Keep the `/app/data` volume: it holds the list of processed jobs and the results.

## Make it yours

Replace `handle_result(job)` in `receiver.py`: write to your database, notify a channel, start the next step.
`job["data"]` is the converted document (or the fields of your JSON Schema), `job["status"]` is `completed` or `failed`.

**Keep a fallback.** There are no retries: if your receiver is down when the job ends, the event is lost. Poll
`GET /v1/jobs` now and then for jobs you are still waiting for; results stay available for 24 hours.

## Settings

| Variable | Default | |
|---|---|---|
| `DOCSLICE_API_KEY` | - | required |
| `WEBHOOK_SECRET` | - | required, at least 16 random characters |
| `PORT` | `8000` | |
| `RESULTS_DIR` | `results` | where confirmed jobs are saved |
| `EVENTS_DB` | `events.db` | SQLite file with the processed job ids |
| `DOCSLICE_API_URL` | `https://api.docslice.app` | |

## Test

```bash
python3 -m unittest       # offline: a real local server, the API simulated
```

More examples: [docslice-examples](https://github.com/docslice/docslice-examples). MIT License.
