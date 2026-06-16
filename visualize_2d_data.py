import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from pathlib import Path
from dotenv import load_dotenv

def load_visualization_config():
    """Loads and validates configuration from the .env file needed for visualization."""
    load_dotenv()
    
    config = {
        'model_name': os.getenv('MODEL_NAME'),
        # Split comma-separated string into a list of case sets, stripping whitespace
        'case_set_names': [cs.strip() for cs in os.getenv('CASE_SET_NAME', '').split(',') if cs.strip()],
    }
    
    # Basic validation
    missing_vars = [k for k, v in config.items() if not v]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
    return config

def plot_polarization_curves(model_name, case_set_names, reference_csv_path):
    """Creates visualization by reading exclusively from the locally saved data directory."""
    print("\n--- Generating Visualization from Local Data ---")
    plt.figure(figsize=(10, 6))
    matplotlib.rcParams.update({'font.size': 12})
    
    cd_key = 'current_density__mea_flow_channels'
    cv_key = 'cell_voltage__mea_flow_channels'
    
    for case_set in case_set_names:
        case_set_dir = Path("data") / model_name / case_set
        if not case_set_dir.exists():
            print(f"Warning: Local data directory for {case_set} not found. Skipping plot.")
            continue
            
        current_densities = []
        cell_voltages = []
        
        for case_dir in case_set_dir.iterdir():
            if case_dir.is_dir():
                res_csv = case_dir / 'results_2d.csv'
                if res_csv.exists():
                    df = pd.read_csv(res_csv)
                    
                    if cd_key in df.columns and cv_key in df.columns:
                        # Append the last recorded value of the simulation for this case
                        current_densities.append(df[cd_key].iloc[-1])
                        cell_voltages.append(df[cv_key].iloc[-1])
                        
        if current_densities:
            cd_arr = np.array(current_densities) / 10000.0  # Convert to A/cm²
            cv_arr = np.array(cell_voltages)
            
            # Sort coordinates by current density to plot a proper smooth line
            sort_idx = np.argsort(cd_arr)
            plt.plot(cd_arr[sort_idx], cv_arr[sort_idx], marker='o', linestyle='-', label=f'CFD - {case_set}')
            
    # Load and plot experimental measurement reference
    if os.path.exists(reference_csv_path):
        measurement_data = pd.read_csv(reference_csv_path)
        plt.plot(measurement_data['current_density_A_cm-2'], measurement_data['voltage_V'], 
                 marker='x', label='Measurement', linestyle='-', color='red')
                 
    plt.xlabel('Current Density / A/cm²')
    plt.ylabel('Cell Voltage / V')
    plt.title(f'Polarization Curves: {model_name}')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    save_path = Path("data") / "polarization_curves.png"
    plt.savefig(save_path, bbox_inches='tight')
    print(f"Plot saved successfully to {save_path}")
    plt.show()

if __name__ == "__main__":
    config = load_visualization_config()
    
    ref_data_path = Path('reference_data') / 'pem_west_measurement_70C.csv'
    plot_polarization_curves(config['model_name'], config['case_set_names'], ref_data_path)