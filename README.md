# AVL-FIRE-RDM

Repository for Research Data Management for CFD Simulations with AVL FIRE

## Requirements

1. Create and activate a virtual environment (optional but recommended):

    ```bash
    # Linux / macOS
    python -m venv .venv
    source .venv/bin/activate
    # Windows (PowerShell)
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    ```

2. Install requirements:

    ```bash
    pip install -r requirements.txt
    ```

## EnSight 3D Results

For 3D CFD fields, a good addition to the current `.asix` + `.csv` pipeline is:

- EnSight as source format
- `XDMF + HDF5` as analysis/archive format

This repo now includes a minimal converter sketch in `src/ensight_to_xdmf.py`.

Recommended optional dependencies:

```bash
pip install pyvista meshio h5py
```

Example usage:

```python
from pathlib import Path

from src.ensight_to_xdmf import EnsightConversionConfig, convert_ensight_case

metadata = convert_ensight_case(
    EnsightConversionConfig(
        case_file=Path(r"path\to\results.case"),
        output_dir=Path(r"artifacts\case_001\3d_results"),
        case_id="case_001",
        point_fields=["temperature", "velocity"],
        cell_fields=["pressure"],
    )
)
```

Produced files:

- `fields.xdmf`: mesh/field descriptor for ParaView and Python tools
- `fields.h5`: binary array storage
- `metadata.json`: case-level linkage back to the existing pipeline

Suggested artifact layout per case:

```text
case_001/
  input/
    *.asix
  results/
    *.csv
    3d_results/
      fields.xdmf
      fields.h5
      metadata.json
```

Suggested integration rule:

- keep `.asix` as the source of case metadata and naming
- keep `.csv` as reduced scalar outputs
- store full 3D fields separately under `3d_results/`
- link all three by the same `case_id`
