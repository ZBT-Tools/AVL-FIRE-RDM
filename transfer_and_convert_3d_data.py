from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from pathlib import PurePosixPath

import dotenv
import paramiko

from src.ensight_to_xdmf import EnsightConversionConfig, convert_ensight_case, inspect_ensight_case
from src import utils


DEFAULT_REMOTE_DATA_DIRECTORY = "results/3D_EnSight"
DEFAULT_LOCAL_DOWNLOAD_DIR = 
DEFAULT_OUTPUT_DIR = "3D_Converted"
ENSIGHT_CASE_NAME


def main() -> int:

    dotenv.load_dotenv()
    hostname = os.getenv("HOSTNAME")
    user = os.getenv("USER")
    password = os.getenv("PASSWORD")
    project_directory = os.getenv("PROJECT_DIRECTORY")
    model_name = os.getenv("MODEL_NAME")
    case_set_name = os.getenv("CASE_SET_NAME")
    case_name = os.getenv("CASE_NAME", default=None)
    
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

    data_directory = 'results/3D_EnSight'
    results_3d_data_paths = utils.retrieve_avl_fire_data_paths(
        sftp_client=sftp_client,
        project_directory=project_directory,
        model_name=model_name,
        case_set_name=case_set_name,
        data_directory=data_directory,
    )

    local_ensight_paths = [os.path.join('data', path.split('.')[-1]) for path in results_3d_data_paths]
    # for i, path in enumerate(results_3d_data_paths):
    #     utils.sftp_get_dir(sftp_client, path, local_ensight_paths[i])

    local_converted_paths = [os.path.join(os.path.split(path)[0], '3D_Converted') for path in local_ensight_paths]
    case_id = model_name + "_DOM_8_0"
    for i in range(len(local_converted_paths)):    
        metadata = convert_ensight_case(
        EnsightConversionConfig(
            case_file=Path(os.path.join(local_ensight_paths[i], case_id + ".case")),
            output_dir=Path(local_converted_paths[i]),
            case_id=case_id,
            )
        )
if __name__ == "__main__":
    raise SystemExit(main())
