from __future__ import annotations

import datetime
import posixpath
import stat
import errno
import re
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


def env_flag(value: str | None, default: bool = False) -> bool:
    """Parse a typical environment-variable boolean value."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"Unsupported boolean value: {value!r}")


def sftp_get_ensight_case_dir(
    sftp: Any,
    remote_dir: str,
    local_dir: str | Path,
    *,
    case_file_name: str,
    only_last_time: bool = False,
) -> None:
    """Download an EnSight case directory, optionally restricted to the final timestep."""
    if not only_last_time:
        sftp_get_dir(sftp, remote_dir, local_dir)
        return

    local_path = Path(local_dir)
    local_path.mkdir(parents=True, exist_ok=True)

    remote_case_path = posixpath.join(remote_dir, case_file_name)
    local_case_path = local_path / case_file_name
    sftp.get(remote_case_path, str(local_case_path))

    case_definition = _read_ensight_case_definition(local_case_path.read_text(encoding="utf-8"))
    geometry_relative_path = case_definition["geometry_model"]
    if geometry_relative_path:
        _sftp_get_relative_file(sftp, remote_dir, local_path, geometry_relative_path)

    variable_relative_paths = case_definition["variable_relative_paths"]
    if not variable_relative_paths:
        return

    last_step_number = _last_ensight_step_number(case_definition)
    resolved_relative_paths = {
        _resolve_ensight_relative_path_for_step(relative_path, last_step_number)
        for relative_path in variable_relative_paths
    }
    for relative_path in sorted(resolved_relative_paths):
        _sftp_get_relative_file(sftp, remote_dir, local_path, relative_path)


def case_name_from_remote_path(remote_path: str) -> str:
    """Extract the case name from an AVL FIRE remote path."""
    project_folder = remote_path.strip("/").split("/")[-3]
    return project_folder.split(".")[-1]


def local_case_dir(model_name: str, case_set_name: str, case_name: str) -> Path:
    """Build the local directory for a single case."""
    return Path("data") / model_name / case_set_name / case_name


def _read_ensight_case_definition(case_text: str) -> dict[str, Any]:
    geometry_model = None
    variable_relative_paths: list[str] = []
    number_of_steps = None
    filename_start_number = None
    filename_increment = None
    section = None

    for raw_line in case_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line in {"FORMAT", "GEOMETRY", "VARIABLE", "TIME"}:
            section = line
            continue

        if section == "GEOMETRY" and line.startswith("model:"):
            geometry_model = line.split(None, 2)[-1]
            continue

        if section == "VARIABLE":
            parts = line.split()
            if parts:
                variable_relative_paths.append(parts[-1])
            continue

        if section == "TIME":
            if line.startswith("number of steps:"):
                number_of_steps = int(line.split(":", 1)[1].strip())
            elif line.startswith("filename start number:"):
                filename_start_number = int(line.split(":", 1)[1].strip())
            elif line.startswith("filename increment:"):
                filename_increment = int(line.split(":", 1)[1].strip())

    return {
        "geometry_model": geometry_model,
        "variable_relative_paths": variable_relative_paths,
        "number_of_steps": number_of_steps,
        "filename_start_number": filename_start_number,
        "filename_increment": filename_increment,
    }


def _last_ensight_step_number(case_definition: dict[str, Any]) -> int:
    number_of_steps = case_definition["number_of_steps"]
    filename_start_number = case_definition["filename_start_number"]
    filename_increment = case_definition["filename_increment"]
    if number_of_steps is None or filename_start_number is None or filename_increment is None:
        raise ValueError("EnSight case file is missing TIME section information for selective retrieval")
    return filename_start_number + (number_of_steps - 1) * filename_increment


def _resolve_ensight_relative_path_for_step(relative_path: str, step_number: int) -> str:
    wildcard_match = re.search(r"\*+", relative_path)
    if wildcard_match is None:
        return relative_path

    width = wildcard_match.end() - wildcard_match.start()
    step_token = f"{step_number:0{width}d}"
    return relative_path[:wildcard_match.start()] + step_token + relative_path[wildcard_match.end():]


def _sftp_get_relative_file(
    sftp: Any,
    remote_dir: str,
    local_dir: Path,
    relative_path: str,
) -> None:
    remote_path = posixpath.join(remote_dir, relative_path)
    local_path = local_dir.joinpath(*relative_path.split("/"))
    local_path.parent.mkdir(parents=True, exist_ok=True)
    sftp.get(remote_path, str(local_path))
