"""Start an asynchronous conversion that calls your receiver when it ends.

    python submit.py invoice.pdf https://your-host.example/webhooks/<WEBHOOK_SECRET>
"""
import json
import mimetypes
import os
import sys
import urllib.request
import uuid

API = os.environ.get("DOCSLICE_API_URL", "https://api.docslice.app")


def multipart(fields: dict, file_path: str):
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    name = os.path.basename(file_path)
    kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(file_path, "rb") as handle:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                     f"Content-Type: {kind}\r\n\r\n".encode() + handle.read() + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    body, content_type = multipart({"format": "json", "mode": "async", "webhook_url": sys.argv[2]}, sys.argv[1])
    request = urllib.request.Request(f"{API}/v1/convert", data=body, method="POST", headers={
        "Authorization": f"Bearer {os.environ['DOCSLICE_API_KEY']}", "Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=120) as response:
        print(json.dumps(json.load(response), indent=2))   # 202 with the job_id


if __name__ == "__main__":
    main()
