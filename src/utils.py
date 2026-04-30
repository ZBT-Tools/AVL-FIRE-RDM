from __future__ import annotations

import datetime
import posixpath
import stat
import errno
from pathlib import Path
from typing import Any


def json_default(obj: Any) -> Any:
    """JSON serializer for values not handled by the standard encoder."""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def retrieve_avl_fire_data_paths(
    sftp_client: Any,
    project_directory: str,
    model_name: str,
    case_set_name: str,
    data_directory: str,
    file_extension: str = None,
    case_name: str | None = None,
) -> list[str]:
    simulation_project_path = f"{project_directory}/simulation/project/"
    if case_name is None:
        print("case_name is None, searching for all cases in the specified model and case set...")
        data_paths: list[str] = []
        for entry in sftp_client.listdir_attr(simulation_project_path):
            if stat.S_ISDIR(entry.st_mode) and f"{model_name}.{case_set_name}." in entry.filename:
                case_path = f"{simulation_project_path}{entry.filename}"
                if file_extension is None:
                    data_path = f"{case_path}/{data_directory}"
                else:
                    data_path = f"{case_path}/{data_directory}/{model_name}{file_extension}"
                try:
                    sftp_client.stat(data_path)
                except IOError as e:
                    print(f"Not found: {entry.filename}, data path: {data_path}")
                else:
                    data_paths.append(data_path)
                    print(f"Found case: {entry.filename}, data path: {data_path}")
    else:
        case_set_path = f"{simulation_project_path}{model_name}.{case_set_name}"
        if file_extension is None:
            data_path = f"{case_set_path}.{case_name}/{data_directory}"    
        else:
            data_path = f"{case_set_path}.{case_name}/{data_directory}/{model_name}{file_extension}"
        print(f"Using specified case_name: {case_name}, data path: {data_path}")
        data_paths = [f"{data_path}"]
    return data_paths


def sftp_get_dir(sftp: Any, remote_dir: str, local_dir: str | Path) -> None:
    """Recursively download a remote directory through a Paramiko SFTP client."""
    local_path = Path(local_dir)
    local_path.mkdir(parents=True, exist_ok=True)

    for entry in sftp.listdir_attr(remote_dir):
        remote_path = posixpath.join(remote_dir, entry.filename)
        local_entry_path = local_path / entry.filename

        if stat.S_ISDIR(entry.st_mode):
            sftp_get_dir(sftp, remote_path, local_entry_path)
            continue

        sftp.get(remote_path, str(local_entry_path))
