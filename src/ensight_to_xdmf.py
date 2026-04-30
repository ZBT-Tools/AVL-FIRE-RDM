from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np

try:
    import meshio
except ImportError:  # pragma: no cover - optional dependency
    meshio = None

try:
    import pyvista as pv
except ImportError:  # pragma: no cover - optional dependency
    pv = None


VTK_TO_MESHIO = {
    1: "vertex",
    3: "line",
    5: "triangle",
    9: "quad",
    10: "tetra",
    12: "hexahedron",
    13: "wedge",
    14: "pyramid",
    15: "penta_prism",
    16: "hexahedron20",
    21: "line3",
    22: "triangle6",
    23: "quad8",
    24: "tetra10",
    25: "hexahedron27",
    26: "wedge15",
    27: "wedge18",
    28: "pyramid13",
}


@dataclass(frozen=True)
class EnsightConversionConfig:
    case_file: Path
    output_dir: Path
    case_id: Optional[str] = None
    point_fields: Optional[Sequence[str]] = None
    cell_fields: Optional[Sequence[str]] = None
    time_indices: Optional[Sequence[int]] = None


def inspect_ensight_case(case_file: str | Path) -> dict:
    """Parse a minimal subset of an EnSight Gold case file for inspection."""
    case_path = Path(case_file)
    geometry_model = None
    time_values: list[float] = []
    point_fields: list[str] = []
    cell_fields: list[str] = []
    variable_re = re.compile(r"^(scalar|vector|tensor)\s+per\s+(node|element):\s+\d+\s+(.+?)\s+\*+")

    section = None
    lines = case_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for raw_line in lines:
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
            match = variable_re.match(line)
            if match:
                _, location, name = match.groups()
                if location == "node":
                    point_fields.append(name)
                else:
                    cell_fields.append(name)
            continue

        if section == "TIME":
            if line.startswith("time values:"):
                continue
            try:
                time_values.append(float(line))
            except ValueError:
                pass

    return {
        "case_file": str(case_path),
        "geometry_model": geometry_model,
        "point_fields": point_fields,
        "cell_fields": cell_fields,
        "time_values": time_values,
    }


def convert_ensight_case(config: EnsightConversionConfig) -> dict:
    """
    Convert an EnSight case to an XDMF/HDF5 time series.

    Output layout
    -------------
    <output_dir>/
      metadata.json
      fields.xdmf
      fields.h5

    Notes
    -----
    - `pyvista` is used for EnSight reading.
    - `meshio` writes the XDMF/HDF5 pair.
    - The mesh is written once and timestep fields are appended.
    """
    _require_optional_dependencies()

    case_file = Path(config.case_file)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve()

    reader = pv.get_reader(str(case_file))
    all_time_values = list(_read_time_values(reader))
    selected_time_indices = _normalize_time_indices(config.time_indices, len(all_time_values))

    initial_dataset = _read_dataset_at(reader, selected_time_indices[0])
    mesh, _ = _dataset_to_meshio(
        initial_dataset,
        point_fields=config.point_fields,
        cell_fields=config.cell_fields,
    )

    xdmf_path = output_dir / "fields.xdmf"
    hdf5_path = output_dir / "fields.h5"
    with meshio.xdmf.TimeSeriesWriter(str(xdmf_path)) as writer:
        writer.write_points_cells(mesh.points, mesh.cells)

        for time_index in selected_time_indices:
            dataset = _read_dataset_at(reader, time_index)
            mesh_at_time, _ = _dataset_to_meshio(
                dataset,
                point_fields=config.point_fields,
                cell_fields=config.cell_fields,
            )
            writer.write_data(
                all_time_values[time_index],
                point_data=mesh_at_time.point_data,
                cell_data=mesh_at_time.cell_data,
            )

    generated_hdf5_path = Path.cwd() / hdf5_path.name
    if generated_hdf5_path != hdf5_path and generated_hdf5_path.exists():
        generated_hdf5_path.replace(hdf5_path)

    metadata = {
        "case_id": config.case_id or case_file.stem,
        "source_format": "EnSight",
        "source_path": str(case_file),
        "artifacts": {
            "xdmf": str(xdmf_path),
            "hdf5": str(hdf5_path),
        },
        "time_values": [all_time_values[i] for i in selected_time_indices],
        "point_fields": sorted(mesh.point_data),
        "cell_fields": sorted(mesh.cell_data),
        "mesh": {
            "n_points": int(mesh.points.shape[0]),
            "cell_blocks": [
                {"type": cell_block.type, "count": int(len(cell_block.data))}
                for cell_block in mesh.cells
            ],
        },
    }

    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _require_optional_dependencies() -> None:
    missing = []
    if pv is None:
        missing.append("pyvista")
    if meshio is None:
        missing.append("meshio")
    if missing:
        raise ImportError(
            "Missing optional dependencies for EnSight conversion: "
            + ", ".join(missing)
            + ". Install them with `pip install pyvista meshio h5py`."
        )


def _read_time_values(reader) -> Sequence[float]:
    time_values = getattr(reader, "time_values", None)
    if time_values is None:
        return [0.0]
    values = [float(value) for value in time_values]
    return values or [0.0]


def _normalize_time_indices(time_indices: Optional[Sequence[int]], n_times: int) -> list[int]:
    if n_times < 1:
        return [0]
    if time_indices is None:
        return list(range(n_times))

    normalized = []
    for index in time_indices:
        if index < 0 or index >= n_times:
            raise IndexError(f"time index {index} is out of range for {n_times} steps")
        normalized.append(int(index))
    if not normalized:
        raise ValueError("time_indices must not be empty")
    return normalized


def _read_dataset_at(reader, time_index: int):
    if hasattr(reader, "set_active_time_point"):
        reader.set_active_time_point(time_index)
    elif hasattr(reader, "time_values") and hasattr(reader, "set_active_time_value"):
        reader.set_active_time_value(reader.time_values[time_index])

    dataset = reader.read()
    return _coerce_unstructured_grid(dataset)


def _coerce_unstructured_grid(dataset):
    if isinstance(dataset, pv.MultiBlock):
        blocks = [block for block in dataset if block is not None and block.n_cells > 0]
        if not blocks:
            raise ValueError("EnSight reader returned an empty multiblock dataset")
        if len(blocks) == 1:
            dataset = blocks[0]
        else:
            dataset = dataset.combine()

    if isinstance(dataset, pv.PolyData):
        dataset = dataset.cast_to_unstructured_grid()

    if not isinstance(dataset, pv.UnstructuredGrid):
        raise TypeError(f"unsupported dataset type: {type(dataset)!r}")
    return dataset


def _dataset_to_meshio(dataset, point_fields=None, cell_fields=None):
    points = np.asarray(dataset.points)
    cells, cell_indices = _extract_meshio_cells(dataset)

    selected_point_fields = _select_fields(dataset.point_data.keys(), point_fields)
    point_data = {
        name: np.asarray(dataset.point_data[name])
        for name in selected_point_fields
    }

    selected_cell_fields = _select_fields(dataset.cell_data.keys(), cell_fields)
    cell_data = {
        name: _split_cell_data_by_block(np.asarray(dataset.cell_data[name]), cell_indices)
        for name in selected_cell_fields
    }

    return meshio.Mesh(points=points, cells=cells, point_data=point_data, cell_data=cell_data), cell_indices


def _select_fields(available_fields: Iterable[str], requested_fields: Optional[Sequence[str]]) -> list[str]:
    available = list(available_fields)
    if requested_fields is None:
        return available

    requested = list(requested_fields)
    missing = sorted(set(requested) - set(available))
    if missing:
        raise KeyError(f"requested fields not found: {missing}")
    return requested


def _extract_meshio_cells(dataset) -> tuple[list[tuple[str, np.ndarray]], list[np.ndarray]]:
    cells = np.asarray(dataset.cells)
    connectivity = np.asarray(getattr(dataset, "cell_connectivity", []))
    offsets = np.asarray(dataset.offset)
    cell_types = np.asarray(dataset.celltypes)
    n_cells = int(len(cell_types))

    if len(connectivity) and len(offsets) == n_cells + 1 and int(offsets[-1]) == len(connectivity):
        starts = offsets[:-1]
        ends = offsets[1:]
        connectivity_source = connectivity
        uses_legacy_cells = False
    else:
        # Fall back to the legacy VTK layout where each cell stores its point
        # count inline in `dataset.cells`.
        if len(offsets) == n_cells + 1:
            starts = offsets[:-1]
            ends = offsets[1:]
        elif len(offsets) == n_cells:
            starts = offsets
            ends = np.empty_like(starts)
            if n_cells > 1:
                ends[:-1] = offsets[1:]
            if n_cells > 0:
                ends[-1] = len(cells)
        else:
            raise ValueError(
                f"unexpected VTK offset layout: {len(offsets)} offsets for {n_cells} cells"
            )
        connectivity_source = cells
        uses_legacy_cells = True

    blocks: dict[str, list[np.ndarray]] = {}
    block_indices: dict[str, list[int]] = {}
    for cell_index, (start, end) in enumerate(zip(starts, ends)):
        cell = connectivity_source[start:end]
        if uses_legacy_cells:
            n_points = int(cell[0])
            cell_connectivity = np.asarray(cell[1:1 + n_points], dtype=int)
        else:
            cell_connectivity = np.asarray(cell, dtype=int)

        vtk_type = int(cell_types[cell_index])
        meshio_type = VTK_TO_MESHIO.get(vtk_type)
        if meshio_type is None:
            raise ValueError(f"unsupported VTK cell type {vtk_type} in EnSight dataset")
        blocks.setdefault(meshio_type, []).append(cell_connectivity)
        block_indices.setdefault(meshio_type, []).append(cell_index)

    cell_blocks = [
        (cell_type, np.vstack(connectivity_rows))
        for cell_type, connectivity_rows in blocks.items()
    ]
    index_blocks = [
        np.asarray(indices, dtype=int)
        for indices in block_indices.values()
    ]
    return cell_blocks, index_blocks


def _split_cell_data_by_block(cell_data: np.ndarray, cell_indices: Sequence[np.ndarray]) -> list[np.ndarray]:
    return [cell_data[indices] for indices in cell_indices]
