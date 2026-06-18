from __future__ import annotations

from contextlib import contextmanager

import modal_app.dedup as dedup_mod


def test_seen_set_uses_s3_safe_lock_settings(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, float]] = []

    @contextmanager
    def fake_shared_data_lock(_path, **kwargs):
        calls.append(kwargs)
        yield

    monkeypatch.setattr(dedup_mod, "DEDUP_PATH", tmp_path)
    monkeypatch.setattr(dedup_mod, "shared_data_lock", fake_shared_data_lock)
    monkeypatch.delenv("ALEITHIA_DEDUP_LOCK_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ALEITHIA_DEDUP_LOCK_STALE_SECONDS", raising=False)
    monkeypatch.delenv("ALEITHIA_DEDUP_LOCK_POLL_SECONDS", raising=False)

    seen = dedup_mod.SeenSet("news")
    seen.add("doc-1")
    seen.save()

    assert calls == [
        {
            "timeout_seconds": dedup_mod.DEFAULT_DEDUP_LOCK_TIMEOUT_SECONDS,
            "poll_seconds": dedup_mod.DEFAULT_DEDUP_LOCK_POLL_SECONDS,
            "stale_seconds": dedup_mod.DEFAULT_DEDUP_LOCK_STALE_SECONDS,
        }
    ]


def test_seen_set_lock_timeout_extends_past_configured_stale(monkeypatch) -> None:
    monkeypatch.setenv("ALEITHIA_DEDUP_LOCK_STALE_SECONDS", "90")
    monkeypatch.setenv("ALEITHIA_DEDUP_LOCK_TIMEOUT_SECONDS", "30")
    monkeypatch.delenv("ALEITHIA_DEDUP_LOCK_POLL_SECONDS", raising=False)

    timeout_seconds, poll_seconds, stale_seconds = dedup_mod._dedup_lock_settings()

    assert stale_seconds == 90
    assert timeout_seconds == 120
    assert poll_seconds == dedup_mod.DEFAULT_DEDUP_LOCK_POLL_SECONDS
