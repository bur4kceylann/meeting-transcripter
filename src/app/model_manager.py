"""Whisper modelinin varlığını kontrol eder, yoksa ilerleme bildirerek indirir.

Model, Hugging Face'teki CTranslate2 dönüştürülmüş sürümden (Systran) düz bir
klasöre indirilir; faster-whisper bu klasörü doğrudan yükleyebilir. İndirme
önce `<ad>.partial` klasörüne yapılır ve tüm dosyalar eksiksiz inince yerine
taşınır; böylece yarım model hiçbir zaman "hazır" görünmez.
"""

from __future__ import annotations

import errno
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

MODEL_REPO = "Systran/faster-whisper-medium"
MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
_URL = "https://huggingface.co/{repo}/resolve/main/{name}"
_CHUNK = 1 << 20


class ModelDownloadError(RuntimeError):
    """Model indirilemedi (ağ, sunucu, eksik veri)."""


class DiskFullError(ModelDownloadError):
    """Diskte model için yeterli yer yok."""


class Fetcher(Protocol):
    def size(self, url: str) -> int: ...
    def stream(self, url: str) -> Iterator[bytes]: ...


class HttpxFetcher:
    def __init__(self, timeout: float = 30.0, transport=None) -> None:
        import httpx

        self._httpx = httpx
        # identity: Hugging Face küçük dosyaları gzip'li ve content-length'siz döner;
        # sıkıştırmasız istekte boyut gelir ve indirilen bayt sayısı boyutla birebir eşleşir.
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            transport=transport,
            headers={"Accept-Encoding": "identity"},
        )

    def size(self, url: str) -> int:
        try:
            response = self._client.head(url)
            response.raise_for_status()
            return int(response.headers["content-length"])
        except (self._httpx.HTTPError, KeyError, ValueError) as exc:
            raise ModelDownloadError(f"{url}: {exc}") from exc

    def stream(self, url: str) -> Iterator[bytes]:
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                yield from response.iter_bytes(_CHUNK)
        except self._httpx.HTTPError as exc:
            raise ModelDownloadError(f"{url}: {exc}") from exc


class ModelManager:
    def __init__(
        self,
        models_dir: Path,
        repo: str = MODEL_REPO,
        files: tuple[str, ...] = MODEL_FILES,
        fetcher: Fetcher | None = None,
    ) -> None:
        self._repo = repo
        self._files = files
        self._fetcher = fetcher
        self.model_dir = models_dir / repo.split("/", 1)[1]

    def is_ready(self) -> bool:
        return all((self.model_dir / name).is_file() for name in self._files)

    def download(self, on_progress: Callable[[float], None]) -> None:
        partial = self.model_dir.with_name(self.model_dir.name + ".partial")
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir(parents=True)
        try:
            self._download_into(partial, on_progress)
        except OSError as exc:
            shutil.rmtree(partial, ignore_errors=True)
            if exc.errno == errno.ENOSPC:
                raise DiskFullError(str(exc)) from exc
            raise ModelDownloadError(str(exc)) from exc
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        shutil.rmtree(self.model_dir, ignore_errors=True)
        partial.rename(self.model_dir)

    def _download_into(self, target: Path, on_progress: Callable[[float], None]) -> None:
        fetcher = self._fetcher or HttpxFetcher()
        urls = {name: _URL.format(repo=self._repo, name=name) for name in self._files}
        sizes = {name: fetcher.size(url) for name, url in urls.items()}
        total = sum(sizes.values())
        free = shutil.disk_usage(target).free
        if free < total:
            raise DiskFullError(f"{total} bayt gerekli, {free} bayt boş")

        done = 0
        on_progress(0.0)
        for name, url in urls.items():
            written = 0
            with open(target / name, "wb") as out:
                for chunk in fetcher.stream(url):
                    out.write(chunk)
                    written += len(chunk)
                    done += len(chunk)
                    on_progress(min(done / total, 1.0) if total else 1.0)
            if written != sizes[name]:
                raise ModelDownloadError(f"{name}: eksik indirme ({written}/{sizes[name]} bayt)")
        on_progress(1.0)
