import os
import json
import paramiko
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from src import utils
from src.asix_parser import parse_asix
from src.firem_name_parser_integration import rename_2d_results_columns, load_yaml_from_github

def load_config():
    """Loads and validates configuration from the .env file."""
    load_dotenv()
    
    config = {
        'hostname': os.getenv('HOSTNAME'),
        'user': os.getenv('USER'),
        'password': os.getenv('PASSWORD'),
        'project_directory': os.getenv('PROJECT_DIRECTORY'),
        'model_name': os.getenv('MODEL_NAME'),
        # Split comma-separated string into a list of case sets, stripping whitespace
        'case_set_names': [cs.strip() for cs in os.getenv('CASE_SET_NAME', '').split(',') if cs.strip()],
        'case_name': os.getenv('CASE_NAME')  # Can be None to process all cases
    }
    
    # Basic validation
    missing_vars = [k for k, v in config.items() if not v and k != 'case_name']
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
    return config

def harvest_and_save_data(sftp_client, config):
    """Fetches remote data, parses it, and saves it into the local data/ directory."""
    project_dir = config['project_directory']
    model_name = config['model_name']
    
    # Load naming rules centrally
    rules_path = load_yaml_from_github()
    
    for case_set in config['case_set_names']:
        print(f"\n--- Harvesting data for Case Set: {case_set} ---")
        
        # 1. Retrieve all .asix input files for this case set
        input_data_paths = utils.retrieve_avl_fire_data_paths(
            sftp_client=sftp_client,
            project_directory=project_dir,
            model_name=model_name,
            case_set_name=case_set,
            data_directory='input',
            file_extension='.asix'
        )
        
        for asix_path in input_data_paths:
            case_name = utils.case_name_from_remote_path(asix_path)
            
            print(f"Processing {case_name}...")
            
            # Setup local directory
            local_dir = utils.local_case_dir(model_name, case_set, case_name)
            local_2d_dir = local_dir / '2d_data'
            local_dir.mkdir(parents=True, exist_ok=True)
            local_2d_dir.mkdir(parents=True, exist_ok=True)
            
            # --- Process Input Metadata (.asix) ---
            with sftp_client.open(asix_path, 'r') as asix_file:
                asix_dict = parse_asix(asix_file, always_list=False, keep_all_attributes=True, cast_values=True)
                
            with open(local_dir / 'input.json', 'w', encoding='utf-8') as f:
                json.dump(asix_dict, f, default=utils.json_default, indent=2)
                
            # --- Process 2D Results Data (.csv) ---
            results_path = asix_path.replace('/input/', '/results/').replace('.asix', '.csv')
            try:
                with sftp_client.open(results_path, 'r') as res_file:
                    df_2d = pd.read_csv(res_file, header=[1, 2], sep=';')
                    
                # Rename columns using the parser integration
                df_2d_renamed, _ = rename_2d_results_columns(df_2d, asix_dict, rules_path)
                
                # Save temporarily for downstream steps
                df_2d_renamed.to_csv(local_2d_dir / 'results_2d.csv', index=False)
            except IOError:
                print(f"  Warning: Could not find or read results file {results_path}")

            # --- Process Monitoring Data (_flc.csv) ---
            monitoring_path = asix_path.replace('/input/', '/results/').replace('.asix', '_flc.csv')
            try:
                with sftp_client.open(monitoring_path, 'r') as mon_file:
                    df_flc = pd.read_csv(mon_file, header=[1, 2], sep=';')
                # Save as raw (can be renamed via rules later if needed)
                # Flattening headers to string for simpler saving
                df_flc.columns = ['_'.join(col).strip() for col in df_flc.columns.values]
                df_flc.to_csv(local_2d_dir / 'monitoring_flc.csv', index=False)
            except IOError:
                print(f"  Warning: Could not find or read monitoring file {monitoring_path}")

if __name__ == "__main__":
    config = load_config()
    
    # 1. Remote Connection & Data Harvesting
    print(f"Connecting to {config['hostname']}...")
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh_client.connect(
            hostname=config['hostname'], 
            username=config['user'], 
            password=config['password']
        )
        sftp_client = ssh_client.open_sftp()
        
        harvest_and_save_data(sftp_client, config)
        
    except paramiko.AuthenticationException:
        print("Authentication failed. Check your username and password.")
    except paramiko.SSHException as e:
        print(f"Could not establish SSH connection: {e}")
    finally:
        if 'sftp_client' in locals() and sftp_client:
            sftp_client.close()
        if 'ssh_client' in locals() and ssh_client:
            ssh_client.close()
