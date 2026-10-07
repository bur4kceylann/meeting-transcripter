from __future__ import annotations

import errno
import shutil
from collections import namedtuple

import pytest

from src.app.model_manager import DiskFullError, ModelDownloadError, ModelManager

FILES = ("config.json", "model.bin")
CONTENT = {"config.json": b'{"a": 1}', "model.bin": b"x" * 5000}


class FakeFetcher:
    def __init__(self, content=CONTENT, fail_on=None, truncate=None, oserror=None):
        self.content = content
        self.fail_on = fail_on
        self.truncate = truncate
        self.oserror = oserror

    def _name(self, url):
        return url.rsplit("/", 1)[1]

    def size(self, url):
        return len(self.content[self._name(url)])

    def stream(self, url):
        name = self._name(url)
        data = self.content[name]
        if name == self.truncate:
            data = data[: len(data) // 2]
        for i in range(0, len(data), 1000):
            if name == self.fail_on and i >= 2000:
                raise ModelDownloadError("bağlantı koptu")
            if name == self.oserror and i >= 2000:
                raise OSError(errno.ENOSPC, "No space left on device")
            yield data[i : i + 1000]


def _manager(tmp_path, **kw):
    return ModelManager(tmp_path / "models", repo="Systran/faster-whisper-medium",
                        files=FILES, fetcher=FakeFetcher(**kw))


def test_model_dir_name(tmp_path):
    assert _manager(tmp_path).model_dir == tmp_path / "models" / "faster-whisper-medium"


def test_download_success(tmp_path):
    m = _manager(tmp_path)
    assert not m.is_ready()
    progress = []
    m.download(progress.append)
    assert m.is_ready()
    for name, data in CONTENT.items():
        assert (m.model_dir / name).read_bytes() == data
    assert progress[0] == 0.0
    assert progress[-1] == 1.0
    assert progress == sorted(progress)
    assert not list((tmp_path / "models").glob("*.partial"))


def test_network_failure_leaves_nothing(tmp_path):
    m = _manager(tmp_path, fail_on="model.bin")
    with pytest.raises(ModelDownloadError):
        m.download(lambda p: None)
    assert not m.is_ready()
    assert not m.model_dir.exists()
    assert not list((tmp_path / "models").glob("*.partial"))


def test_truncated_stream_is_error(tmp_path):
    m = _manager(tmp_path, truncate="model.bin")
    with pytest.raises(ModelDownloadError):
        m.download(lambda p: None)
    assert not m.is_ready()


def test_enospc_while_writing_is_disk_full(tmp_path):
    m = _manager(tmp_path, oserror="model.bin")
    with pytest.raises(DiskFullError):
        m.download(lambda p: None)
    assert not list((tmp_path / "models").glob("*.partial"))


def test_not_enough_free_space_up_front(tmp_path, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Usage(10_000, 9_000, 100))
    m = _manager(tmp_path)
    with pytest.raises(DiskFullError):
        m.download(lambda p: None)
    assert not list((tmp_path / "models").glob("*.partial"))


def test_redownload_replaces_previous_partial(tmp_path):
    m = _manager(tmp_path)
    stale = tmp_path / "models" / "faster-whisper-medium.partial"
    stale.mkdir(parents=True)
    (stale / "model.bin").write_bytes(b"eski")
    m.download(lambda p: None)
    assert m.is_ready()
    assert not stale.exists()


def test_httpx_fetcher_requests_uncompressed_size():
    # Hugging Face küçük dosyaları gzip'li ve content-length'siz döner;
    # boyut yalnızca sıkıştırmasız (identity) istekte gelir.
    import httpx

    from src.app.model_manager import HttpxFetcher

    body = b'{"a": 1}'

    def handler(request):
        if request.headers.get("accept-encoding") == "identity":
            return httpx.Response(200, headers={"content-length": str(len(body))}, content=body)
        return httpx.Response(200, headers={"content-encoding": "gzip"})

    fetcher = HttpxFetcher(transport=httpx.MockTransport(handler))
    url = "https://huggingface.co/x/resolve/main/config.json"
    assert fetcher.size(url) == len(body)
    assert b"".join(fetcher.stream(url)) == body
