"""Tests for kbot_client.folder_sync.FolderSync against the fake Kbot server."""

import pytest

from kbot_client import Client
from kbot_client.folder_sync import FolderSync
from tests.fake_kbot import FakeKbot, RecordedRequest

ROOT = "root-uuid"


def create_folder(request: RecordedRequest) -> dict:
    body = request.json()
    return {"uuid": "%s/%s" % (body["parent"], body["name"])}


@pytest.fixture
def local_tree(tmp_path):
    """Local tree:

    already.txt           (already present remotely)
    new.txt
    existing/inner.txt    (folder already present remotely)
    fresh/deep/leaf.txt   (folders missing remotely)
    """
    (tmp_path / "already.txt").write_text("old")
    (tmp_path / "new.txt").write_text("new")
    (tmp_path / "existing").mkdir()
    (tmp_path / "existing" / "inner.txt").write_text("inner")
    (tmp_path / "fresh" / "deep").mkdir(parents=True)
    (tmp_path / "fresh" / "deep" / "leaf.txt").write_text("leaf")
    return tmp_path


@pytest.fixture
def remote(kbot: FakeKbot) -> FakeKbot:
    kbot.route(
        "GET",
        "/api/folder/%s/list/" % ROOT,
        {"folders": [{"name": "existing", "uuid": "existing-uuid"}], "files": [{"name": "already.txt"}]},
    )
    for folder in ("existing-uuid", "%s/fresh" % ROOT, "%s/fresh/deep" % ROOT):
        kbot.route("GET", "/api/folder/%s/list/" % folder, {"folders": [], "files": []})
    kbot.route("POST", "/api/folder/", create_folder)
    kbot.route("POST", "/api/attachment/", {})
    return kbot


def uploads(kbot: FakeKbot) -> set[tuple[str, str, bytes]]:
    result = set()
    for request in kbot.requests_to("POST", "/api/attachment/"):
        form = request.form()
        assert request.query == {"override": ["False"]}
        result.add((form["folder"][1].decode(), form["name"][1].decode(), form["upload_files"][1]))
    return result


@pytest.mark.parametrize("suffix", ["", "/"], ids=["no-trailing-slash", "trailing-slash"])
def test_sync_creates_missing_folders_and_uploads_new_files(remote: FakeKbot, client: Client, local_tree, suffix):
    FolderSync(client).sync(str(local_tree) + suffix, ROOT)

    created = [r.json() for r in remote.requests_to("POST", "/api/folder/")]
    assert created == [
        {"name": "fresh", "parent": ROOT},
        {"name": "deep", "parent": "%s/fresh" % ROOT},
    ]
    assert uploads(remote) == {
        (ROOT, "new.txt", b"new"),
        ("existing-uuid", "inner.txt", b"inner"),
        ("%s/fresh/deep" % ROOT, "leaf.txt", b"leaf"),
    }


def test_sync_of_up_to_date_tree_uploads_nothing(kbot: FakeKbot, client: Client, tmp_path):
    (tmp_path / "already.txt").write_text("old")
    kbot.route("GET", "/api/folder/%s/list/" % ROOT, {"folders": [], "files": [{"name": "already.txt"}]})

    FolderSync(client).sync(str(tmp_path), ROOT)

    assert kbot.requests_to("POST", "/api/attachment/") == []
    assert kbot.requests_to("POST", "/api/folder/") == []
