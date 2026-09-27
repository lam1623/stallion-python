from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from stallion.api import create_app
from stallion.config import AppConfig

from .conftest import requires_ffmpeg

TOKEN = "s3cret-token-for-tests"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>Stallion</title>")
    (root / "assets" / "app-123.js").write_text("console.log('ui')")
    return root


@pytest.fixture
def client(tmp_path: Path, media_dir: Path, static_dir: Path) -> Iterator[TestClient]:
    config = AppConfig(
        auth_token=TOKEN,
        media_roots=[media_dir, tmp_path / "out"],
        data_dir=tmp_path / "data",
        static_dir=static_dir,
        detect_gpu=False,
    )
    (tmp_path / "out").mkdir()
    with TestClient(create_app(config), base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


def test_health_is_public_and_api_is_not(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/system").status_code == 401
    assert client.get("/api/system", headers={"Authorization": "Bearer nope"}).status_code == 401
    system = client.get("/api/system", headers=AUTH).json()
    assert system["ffmpeg"]["available"] is True and system["desktop"] is False
    # GPU detection switched off: settled at once, nothing found
    assert system["hardware"] == {
        "state": "ready",
        "available": False,
        "backend": None,
        "label": None,
        "codecs": [],
        "ten_bit": [],
        "presets": [],
    }


def test_a_stale_cookie_does_not_hide_a_valid_bearer_token(client: TestClient) -> None:
    # E.g. the token was rotated while a browser still holds the old session cookie
    client.cookies.set("stallion_session", "token-from-before-a-rotation")
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/settings", headers=AUTH).status_code == 200
    client.cookies.set("stallion_session", TOKEN)
    assert client.get("/api/settings", headers={"Authorization": "Bearer stale"}).status_code == 200


def test_html_shell_carries_the_saved_theme(tmp_path: Path) -> None:
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text('<!doctype html><html lang="en"><head></head><body></body></html>')
    config = AppConfig(
        auth_token=TOKEN, media_roots=[tmp_path], data_dir=tmp_path / "data", static_dir=ui, detect_gpu=False
    )
    with TestClient(create_app(config)) as client:
        assert '<html data-theme="light" lang="en">' in client.get("/").text
        assert client.put("/api/settings", json={"theme": "dark"}, headers=AUTH).status_code == 200
        page = client.get("/")
        assert '<html data-theme="dark" lang="en">' in page.text
        assert page.headers["cache-control"] == "no-cache" and "etag" not in page.headers


def test_login_flows_set_a_strict_http_only_cookie(client: TestClient) -> None:
    bad = client.get("/auth", params={"token": "wrong"}, follow_redirects=False)
    assert bad.status_code == 303 and bad.headers["location"] == "/?auth=failed"
    good = client.get("/auth", params={"token": TOKEN}, follow_redirects=False)
    cookie = good.headers["set-cookie"]
    assert good.headers["location"] == "/" and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert client.get("/api/auth/status").json() == {"required": True, "authenticated": True}
    assert client.get("/api/presets").status_code == 200

    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"token": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"token": TOKEN}).status_code == 204
    assert client.get("/api/settings").status_code == 200


def test_security_headers_and_static_caching(client: TestClient) -> None:
    index = client.get("/")
    assert index.status_code == 200 and "Stallion" in index.text
    assert index.headers["cache-control"] == "no-cache"
    assert "default-src 'self'" in index.headers["content-security-policy"]
    assert index.headers["x-frame-options"] == "DENY" and index.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self';" in index.headers["content-security-policy"] + ";"
    assert "unsafe-eval" not in index.headers["content-security-policy"]
    asset = client.get("/assets/app-123.js")
    assert "immutable" in asset.headers["cache-control"]


def test_desktop_mode_allows_the_webview_bridge(tmp_path: Path, static_dir: Path) -> None:
    config = AppConfig(
        auth_token=TOKEN, media_roots=[tmp_path], data_dir=tmp_path / "d", static_dir=static_dir
    )
    config.desktop = True
    with TestClient(create_app(config)) as desktop:
        assert "'unsafe-eval'" in desktop.get("/").headers["content-security-policy"]


def test_filesystem_is_confined_to_roots(client: TestClient, media_dir: Path) -> None:
    listing = client.get("/api/fs/list", params={"path": str(media_dir)}, headers=AUTH).json()
    assert "clip.mp4" in [e["name"] for e in listing["entries"]]
    denied = client.get("/api/fs/list", params={"path": "/etc"}, headers=AUTH)
    assert denied.status_code == 403 and denied.json()["code"] == "outside_roots"
    roots = client.get("/api/fs/roots", headers=AUTH).json()
    assert str(media_dir.resolve()) in [r["path"] for r in roots]


def test_settings_validation_and_persistence(client: TestClient, tmp_path: Path) -> None:
    assert client.put("/api/settings", json={"concurrency": 99}, headers=AUTH).status_code == 422
    assert client.put("/api/settings", json={"output_dir": "/etc"}, headers=AUTH).status_code == 403
    assert client.put("/api/settings", json={"default_preset": "nope"}, headers=AUTH).status_code == 422
    ok = client.put(
        "/api/settings", json={"concurrency": 3, "output_dir": str(tmp_path / "out")}, headers=AUTH
    )
    assert ok.status_code == 200 and ok.json()["concurrency"] == 3 and ok.json()["gpu_encoding"] is True
    off = client.put("/api/settings", json={"gpu_encoding": False}, headers=AUTH)
    assert off.status_code == 200 and off.json()["gpu_encoding"] is False
    saved = json.loads((tmp_path / "data" / "settings.json").read_text())
    assert saved["output_dir"] == str((tmp_path / "out").resolve())


def test_layout_is_a_setting_that_survives_restarts(client: TestClient, tmp_path: Path) -> None:
    # The desktop app gets a new origin on every launch, so the window layout lives here
    current = client.get("/api/settings", headers=AUTH).json()
    assert current["queue_layout"] == "table" and current["sheet_height"] is None
    patch = {"queue_layout": "cards", "inspector_pinned": True, "sheet_height": 420, "drawer_width": 520}
    assert client.put("/api/settings", json=patch, headers=AUTH).json()["sheet_height"] == 420
    assert client.put("/api/settings", json={"queue_layout": "grid"}, headers=AUTH).status_code == 422
    assert client.put("/api/settings", json={"sheet_height": 20}, headers=AUTH).status_code == 422
    # null goes back to the default size
    assert (
        client.put("/api/settings", json={"drawer_width": None}, headers=AUTH).json()["drawer_width"] is None
    )
    saved = json.loads((tmp_path / "data" / "settings.json").read_text())
    assert saved["queue_layout"] == "cards" and saved["inspector_pinned"] is True
    assert saved["sheet_height"] == 420 and saved["drawer_width"] is None


@requires_ffmpeg
def test_more_formats_for_a_file_over_http(client: TestClient, media_dir: Path) -> None:
    added = client.post("/api/jobs", json={"paths": [str(media_dir / "clip.mp4")]}, headers=AUTH).json()
    source = added["jobs"][0]
    response = client.post(
        "/api/jobs/formats", json={"ids": [source["id"], "missing"], "preset_id": "mp3"}, headers=AUTH
    )
    assert response.status_code == 200
    body = response.json()
    [extra] = body["jobs"]
    assert extra["input_path"] == source["input_path"] and extra["options"]["preset_id"] == "mp3"
    assert [e["code"] for e in body["errors"]] == ["job_not_found"]
    listed = [job["id"] for job in client.get("/api/jobs", headers=AUTH).json()["jobs"]]
    assert listed == [source["id"], extra["id"]]
    unknown = client.post(
        "/api/jobs/formats", json={"ids": [source["id"]], "preset_id": "nope"}, headers=AUTH
    )
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_preset"


def test_presets_and_fonts(client: TestClient) -> None:
    presets = client.get("/api/presets", headers=AUTH).json()
    assert len(presets) == 34 and all("available" in p for p in presets)
    assert presets[0]["category"] == "video"
    assert isinstance(client.get("/api/fonts", headers=AUTH).json(), list)


def test_websocket_requires_auth_and_same_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as err, client.websocket_connect("/api/events") as ws:
        ws.receive_json()
    assert err.value.code == 4401
    with (
        pytest.raises(WebSocketDisconnect) as err,
        client.websocket_connect(
            f"/api/events?token={TOKEN}", headers={"Origin": "https://evil.example"}
        ) as ws,
    ):
        ws.receive_json()
    assert err.value.code == 4403
    with client.websocket_connect(
        f"/api/events?token={TOKEN}", headers={"Origin": "http://testserver"}
    ) as ws:
        assert ws.receive_json()["type"] == "snapshot"


@requires_ffmpeg
def test_full_conversion_over_http(client: TestClient, media_dir: Path, tmp_path: Path) -> None:
    client.put("/api/settings", json={"output_dir": str(tmp_path / "out")}, headers=AUTH)
    added = client.post(
        "/api/jobs",
        json={"paths": [str(media_dir / "clip.mp4"), "/etc/passwd"], "options": {"preset_id": "webm-vp9"}},
        headers=AUTH,
    ).json()
    assert [e["code"] for e in added["errors"]] == ["outside_roots"]
    job_id = added["jobs"][0]["id"]
    assert (
        client.patch(f"/api/jobs/{job_id}", json={"options": {"speed": "fast"}}, headers=AUTH).status_code
        == 200
    )
    bad = client.patch(f"/api/jobs/{job_id}", json={"options": {"audio_track": 7}}, headers=AUTH)
    assert bad.status_code == 422 and bad.json()["code"] == "bad_audio_track"
    assert "libvpx-vp9" in client.get(f"/api/jobs/{job_id}/log", headers=AUTH).json()["command"]

    with client.websocket_connect(f"/api/events?token={TOKEN}") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        assert client.post("/api/queue/start", headers=AUTH).json()["running"] is True
        types = set()
        while "queue_finished" not in types:
            types.add(ws.receive_json()["type"])
    job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
    assert job["status"] == "completed" and Path(job["output_path"]).name == "clip.webm"

    deadline = time.monotonic() + 20
    while client.get(f"/api/jobs/{job_id}/thumbnail", headers=AUTH).status_code != 200:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    assert client.post(f"/api/jobs/{job_id}/pause", headers=AUTH).status_code == 409
    assert client.post("/api/queue/clear", json={"statuses": ["completed"]}, headers=AUTH).json()[
        "removed"
    ] == [job_id]
    assert client.get(f"/api/jobs/{job_id}", headers=AUTH).status_code == 404
