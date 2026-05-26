from __future__ import annotations

import numpy as np
import pyvista as pv

from src.ensight_to_xdmf import _dataset_to_meshio


def _make_block(origin_x: float) -> pv.UnstructuredGrid:
    points = np.array(
        [
            [origin_x + 0.0, 0.0, 0.0],
            [origin_x + 1.0, 0.0, 0.0],
            [origin_x + 1.0, 1.0, 0.0],
            [origin_x + 0.0, 1.0, 0.0],
            [origin_x + 0.0, 0.0, 1.0],
            [origin_x + 1.0, 0.0, 1.0],
            [origin_x + 1.0, 1.0, 1.0],
            [origin_x + 0.0, 1.0, 1.0],
        ],
        dtype=float,
    )
    cells = np.array([8, 0, 1, 2, 3, 4, 5, 6, 7])
    cell_types = np.array([pv.CellType.HEXAHEDRON], dtype=np.uint8)
    return pv.UnstructuredGrid(cells, cell_types, points)


def test_multiblock_cell_fields_preserve_union_with_nan_padding():
    block_a = _make_block(0.0)
    block_b = _make_block(2.0)

    block_a.cell_data["shared"] = np.array([1.0])
    block_b.cell_data["shared"] = np.array([2.0])
    block_a.cell_data["volume_only"] = np.array([10.0])

    dataset = pv.MultiBlock([block_a, block_b])
    mesh, _ = _dataset_to_meshio(dataset)

    assert sorted(mesh.cell_data) == ["shared", "volume_only"]
    assert mesh.cell_data["shared"][0].tolist() == [1.0, 2.0]

    volume_only = mesh.cell_data["volume_only"][0]
    assert volume_only.shape == (2,)
    assert volume_only[0] == 10.0
    assert np.isnan(volume_only[1])
