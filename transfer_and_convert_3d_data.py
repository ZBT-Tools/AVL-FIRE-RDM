from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import dotenv
import paramiko

from src.ensight_to_xdmf import EnsightConversionConfig, convert_ensight_case
from src import utils


DEFAULT_REMOTE_DATA_DIRECTORY = "results/3D_EnSight"
DEFAULT_LOCAL_3D_DIR = "3d_data"
DEFAULT_OUTPUT_DIR = "3D_Converted"


def main() -> int:

    dotenv.load_dotenv()
    hostname = os.getenv("HOSTNAME")
    user = os.getenv("USER")
    password = os.getenv("PASSWORD")
    project_directory = os.getenv("PROJECT_DIRECTORY")
    model_name = os.getenv("MODEL_NAME")
    case_set_names = [cs.strip() for cs in os.getenv("CASE_SET_NAME", "").split(",") if cs.strip()]
    case_name = os.getenv("CASE_NAME", default=None)
    if case_name == "None":
        case_name = None
    only_last_time = utils.env_flag(os.getenv("ONLY_LAST_TIME_STEP"), default=True)
    retrieve_only_last_time = utils.env_flag(
        os.getenv("RETRIEVE_ONLY_LAST_TIME_STEP"),
        default=only_last_time,
    )
    
     # --- SSH Client Initialization ---
    ssh_client = paramiko.SSHClient()
    # Automatically add the server's host key. For production, it's better to manage known_hosts explicitly.
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Connect to the SSH server
        ssh_client.connect(hostname=hostname, username=user, password=password)
        print(f"Connected to {hostname} using password.")

        # Open an SFTP client
        sftp_client = ssh_client.open_sftp()
        print(f"Opened SFTP session.")
    except paramiko.AuthenticationException:
        print("Authentication failed. Check your username, password, or private key.")
    except paramiko.SSHException as e:
        print(f"Could not establish SSH connection: {e}")

    data_directory = DEFAULT_REMOTE_DATA_DIRECTORY
    case_id = model_name + "_DOM_8_0"
    for case_set_name in case_set_names:
        results_3d_data_paths = utils.retrieve_avl_fire_data_paths(
            sftp_client=sftp_client,
            project_directory=project_directory,
            model_name=model_name,
            case_set_name=case_set_name,
            data_directory=data_directory,
            case_name=case_name,
        )

        local_ensight_paths: list[Path] = []
        for path in results_3d_data_paths:
            current_case_name = utils.case_name_from_remote_path(path)
            local_case_dir = utils.local_case_dir(model_name, case_set_name, current_case_name)
            local_ensight_dir = local_case_dir / DEFAULT_LOCAL_3D_DIR
            utils.sftp_get_ensight_case_dir(
                sftp_client,
                path,
                local_ensight_dir,
                case_file_name=f"{case_id}.case",
                only_last_time=retrieve_only_last_time,
            )
            local_ensight_paths.append(local_ensight_dir)

        local_converted_paths = [path / DEFAULT_OUTPUT_DIR for path in local_ensight_paths]
        for i in range(len(local_converted_paths)):
            metadata = convert_ensight_case(
                EnsightConversionConfig(
                    case_file=local_ensight_paths[i] / f"{case_id}.case",
                    output_dir=local_converted_paths[i],
                    case_id=case_id,
                ),
                only_last_time=only_last_time,
                )
if __name__ == "__main__":
    raise SystemExit(main())
