"""An in-memory stand-in for the Google Drive v3 REST API (the parts SciLibra uses)."""

import hashlib
import itertools
import json
import re

import requests

from scilibra.core.gdrive import API, FOLDER_MIME, UPLOAD_API


class FakeResponse:
    def __init__(self, status, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]


class FakeDrive:
    def __init__(self):
        self.files = {}      # id -> metadata (+ "_content")
        self.uploads = {}    # upload url -> (file id or None, metadata, bytearray)
        self.ids = (f"id{n}" for n in itertools.count(1))
        self.offline = False
        self.requests = []   # (method, url) log
        self.upload_count = 0
        self.put_errors = []     # HTTP status codes to answer the next upload PUTs with (e.g. [502])
        self.lose_chunk = False  # when failing a PUT, drop its data (like a broken connection)

    # helpers for tests
    def by_name(self, name):
        return [f for f in self.files.values() if f["name"] == name and not f.get("trashed")]

    def content(self, name):
        return self.by_name(name)[0]["_content"]

    def children(self, parent):
        return [f for f in self.files.values() if parent in f.get("parents", []) and not f.get("trashed")]

    def _public(self, f):
        return {k: v for k, v in f.items() if not k.startswith("_")}

    def _check(self):
        if self.offline:
            raise requests.ConnectionError("network is down")

    # requests-style API
    def get(self, url, params=None, **_kw):
        self._check()
        self.requests.append(("GET", url))
        params = params or {}
        if url == f"{API}/files":
            q = params["q"]
            parent = re.search(r"'([^']+)' in parents", q).group(1)
            name = re.search(r"name = '((?:[^'\\]|\\.)*)'", q)
            name = name.group(1).replace("\\'", "'") if name else None
            found = [self._public(f) for f in self.children(parent)
                     if (name is None or f["name"] == name)
                     and ("mimeType = " not in q or f["mimeType"] == FOLDER_MIME)]
            return FakeResponse(200, {"files": found})
        file_id = url.rsplit("/", 1)[1]
        f = self.files.get(file_id)
        if f is None:
            return FakeResponse(404, {"error": {"message": "File not found"}})
        if params.get("alt") == "media":
            return FakeResponse(200, content=bytes(f["_content"]))
        return FakeResponse(200, self._public(f))

    def post(self, url, params=None, json=None, headers=None, **_kw):
        self._check()
        self.requests.append(("POST", url))
        if url == f"{API}/files":  # folder
            file_id = next(self.ids)
            self.files[file_id] = {"id": file_id, "name": json["name"], "mimeType": json["mimeType"],
                                   "parents": json.get("parents", ["root"]), "trashed": False}
            return FakeResponse(200, {"id": file_id})
        if url == f"{UPLOAD_API}/files":
            location = f"https://upload.fake/{len(self.uploads)}"
            self.uploads[location] = (None, dict(json), bytearray())
            return FakeResponse(200, {}, headers={"Location": location})
        raise AssertionError(url)

    def patch(self, url, params=None, json=None, headers=None, **_kw):
        self._check()
        self.requests.append(("PATCH", url))
        file_id = url.rsplit("/", 1)[1]
        if file_id not in self.files:
            return FakeResponse(404, {"error": {"message": "File not found"}})
        location = f"https://upload.fake/{len(self.uploads)}"
        self.uploads[location] = (file_id, dict(json or {}), bytearray())
        return FakeResponse(200, {}, headers={"Location": location})

    def put(self, url, data=None, headers=None, **_kw):
        self._check()
        file_id, meta, buffer = self.uploads[url]
        content_range = headers["Content-Range"]
        total = int(content_range.rsplit("/", 1)[1])
        if content_range.startswith("bytes */") and not data and total:  # status query
            if len(buffer) < total:
                return FakeResponse(308, {}, headers={"Range": f"bytes=0-{len(buffer) - 1}"} if buffer else {})
        else:
            if self.put_errors:
                status = self.put_errors.pop(0)
                if not self.lose_chunk:
                    start = int(content_range.split()[1].split("-")[0])
                    del buffer[start:]
                    buffer.extend(data)
                return FakeResponse(status, {"error": {"message": "Bad Gateway"}})
            start = int(content_range.split()[1].split("-")[0]) if not content_range.startswith("bytes */") else 0
            del buffer[start:]
            buffer.extend(data)
            if len(buffer) < total:
                return FakeResponse(308, {}, headers={"Range": f"bytes=0-{len(buffer) - 1}"})
        self.upload_count += 1
        if file_id is None:
            file_id = next(self.ids)
            self.files[file_id] = {"id": file_id, "parents": meta.get("parents", ["root"]),
                                   "mimeType": "application/octet-stream", "trashed": False}
        f = self.files[file_id]
        f.update(name=meta.get("name", f.get("name")), _content=bytes(buffer), size=str(len(buffer)),
                 md5Checksum=hashlib.md5(bytes(buffer)).hexdigest())
        f["_revisions"] = f.get("_revisions", 0) + 1
        return FakeResponse(200, self._public(f))

    def delete(self, url, **_kw):
        self._check()
        file_id = url.rsplit("/", 1)[1]
        self.files.pop(file_id, None)
        return FakeResponse(204, {})

    def trash(self, name):
        for f in self.by_name(name):
            f["trashed"] = True


def fake_token(path, email="scientist@example.com"):
    with open(path, "w") as fh:
        json.dump({"token": "t", "refresh_token": "r", "client_id": "c", "client_secret": "s",
                   "scopes": [], "scilibra_email": email}, fh)


