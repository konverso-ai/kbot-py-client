"""Live File Manager tests (upload, FolderSync) inside a disposable sandbox folder."""

import pytest

from kbot_client import Client
from kbot_client.folder_sync import FolderSync
from tests.live.helpers import ListRecorder

pytestmark = pytest.mark.live


def remote_tree(cli: Client, folder: str, prefix: str = "") -> dict[str, int]:
    """Map every remote file path below ``folder`` to its size."""
    listing = cli.request("get", uri="folder/%s/list" % folder)
    listing.raise_for_status()
    tree = {prefix + f["name"]: f["size"] for f in listing.json().get("files", [])}
    for sub_folder in listing.json().get("folders", []):
        tree.update(remote_tree(cli, sub_folder["uuid"], prefix + sub_folder["name"] + "/"))
    return tree


def test_post_file_uploads_into_folder(live_client: Client, sandbox_folder: str, tmp_path):
    document = tmp_path / "report.txt"
    document.write_bytes(b"kbot-py-client live test")

    with document.open("rb") as fd:
        response = live_client.post_file(
            "attachment",
            data={"folder": sandbox_folder, "name": "report.txt"},
            params={"override": False},
            files={"upload_files": ("report.txt", fd, "text/plain")},
        )

    assert response.status_code == 201
    assert response.json()["folder_uuid"] == sandbox_folder
    assert remote_tree(live_client, sandbox_folder) == {"report.txt": 24}


def test_folder_sync_mirrors_local_tree_then_does_nothing(live_client: Client, sandbox_folder: str, tmp_path):
    (tmp_path / "a.txt").write_bytes(b"a")
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    (tmp_path / "sub" / "c.txt").write_bytes(b"cc")
    (tmp_path / "sub" / "deep" / "b.txt").write_bytes(b"bbb")
    syncer = FolderSync(live_client)

    syncer.sync(str(tmp_path), sandbox_folder)

    assert remote_tree(live_client, sandbox_folder) == {"a.txt": 1, "sub/c.txt": 2, "sub/deep/b.txt": 3}

    recorder = ListRecorder()
    live_client.recorder = recorder
    syncer.sync(str(tmp_path) + "/", sandbox_folder)

    assert [(method, url) for method, url, *_ in recorder.calls if method != "get"] == []
    assert remote_tree(live_client, sandbox_folder) == {"a.txt": 1, "sub/c.txt": 2, "sub/deep/b.txt": 3}
