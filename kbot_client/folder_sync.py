
import os

from kbot_client.client import Client


class FolderSync:  # noqa: D101
    def __init__(self, client: Client) -> None:  # noqa: D107
        self._client = client

    @property
    def client(self) -> Client:  # noqa: D102
        return self._client

    def sync(self, top_unix_folder: str, remote_folder_uuid: str) -> None:  # noqa: C901, PLR0912
        """Will sync the unix path "path" inside the target folder."""
        folders_to_files = {}
        for root, dirs, files in os.walk(top_unix_folder):

            for d in dirs:
                full_path = os.path.join(root, d)  # noqa: PTH118
                rel_path = full_path[len(top_unix_folder):]

                if os.path.isdir(full_path):  # noqa: PTH112
                    try:
                        folder_files = folders_to_files[rel_path]
                    except KeyError:
                        folder_files = folders_to_files[rel_path] = []

                else:
                    msg = f"Not a folder: {full_path}"
                    raise RuntimeError(msg)

            rel_path = root[len(top_unix_folder):]
            try:
                folder_files = folders_to_files[rel_path]
            except KeyError:
                folder_files = folders_to_files[rel_path] = []

            for f in files:
                folder_files.append(f)

        folder_cache = {}
        for folder, files in folders_to_files.items():
            # Folder is a relative path /a/b/c
            # Make sure the folder is now properly defined in the remote File Manager.
            current_top_folder = remote_folder_uuid
            current_relative_path  = ""
            parts = [d for d in folder.split("/") if d]
            visited_folders = []
            for part in parts:
                visited_folders.append(part)
                current_relative_path = "/".join(visited_folders)


                if current_relative_path in folder_cache:
                    current_top_folder = folder_cache[current_relative_path]
                    continue

                # Lookup the current folder
                response = self.client.request("get", uri=f"folder/{current_top_folder}/list")
                matching_folders = [f for f in response.json().get("folders", []) if f.get("name") == part]
                if matching_folders:
                    current_top_folder = folder_cache[current_relative_path] = matching_folders[0].get("uuid")
                else:
                    response = self.client.request(
                        "post",
                        uri="folder",
                        data={
                            "name": part,
                            "parent": current_top_folder,
                        },
                    )

                    # return "%s %s" % (part, current_top_folder)  # noqa: ERA001
                    current_top_folder = folder_cache[current_relative_path] = response.json().get("uuid")

            # We are now ready to work on the Files
            # Get the current list of files in this folder
            response = self.client.request("get", uri=f"folder/{current_top_folder}/list")
            file_names = [f.get("name") for f in response.json().get("files", [])]
            for f in files:
                if f in file_names:
                    # File is already in the target File Manager
                    continue
                # Make a copy of the file with a proper name
                filepath = os.path.join(top_unix_folder, current_relative_path, f)  # noqa: PTH118
                if not os.path.exists(filepath):  # noqa: PTH110
                    msg = f"File {filepath} does not exists"
                    raise RuntimeError(msg)

                # Upload to remote filemanager
                with open(filepath, "rb") as fd:  # noqa: PTH123
                    _files = {
                        "upload_files": fd,
                    }
                    params= {
                        "override": False,
                    }
                    data = {
                        "folder": current_top_folder,
                        "name": f,
                    }
                    response = self.client.post_file(
                        "attachment",
                        data=data,
                        params=params,
                        files=_files,
                    )
                    # print("Response from API: ", response.text)  # noqa: ERA001
