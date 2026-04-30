from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pyvista as pv
import plotly.graph_objects as go


DEFAULT_XDMF_PATH = Path("3D_Converted") / "fields.xdmf"


def coerce_unstructured_grid(dataset):
    if isinstance(dataset, pv.MultiBlock):
        blocks = [block for block in dataset if block is not None and block.n_cells > 0]
        if not blocks:
            raise ValueError("The XDMF reader returned an empty multiblock dataset.")
        if len(blocks) == 1:
            return blocks[0]
        # Some XDMF exports contain overlapping blocks on identical geometry.
        # Combining them creates coincident cells that can hide the real scalars.
        return max(blocks, key=lambda block: float(np.ptp(block.cell_data.get("Flow_Temperature", [0.0]))))
    return dataset


def load_mesh(xdmf_path: Path, time_index: int):
    if not xdmf_path.exists():
        raise FileNotFoundError(f"XDMF file not found: {xdmf_path.resolve()}")

    reader = pv.get_reader(str(xdmf_path))
    time_values = list(getattr(reader, "time_values", [0.0])) or [0.0]
    if time_index < 0 or time_index >= len(time_values):
        raise IndexError(f"time index {time_index} is out of range for {len(time_values)} steps")

    if hasattr(reader, "set_active_time_point"):
        reader.set_active_time_point(time_index)
    elif hasattr(reader, "set_active_time_value"):
        reader.set_active_time_value(time_values[time_index])

    dataset = reader.read()
    return coerce_unstructured_grid(dataset), time_values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["3d", "2d"], default="3d")
    args = parser.parse_args()

    xdmf_path = Path('data') / 'Case_6' / 'results' / DEFAULT_XDMF_PATH
    field = "Flow_Temperature"
    mesh, time_values = load_mesh(xdmf_path, 10)
    pyvista = False
    if pyvista:
        plotter = pv.Plotter()
        slice_mesh = mesh.slice(normal="x", origin=(0.0, 0.001609, 0.1)).cell_data_to_point_data()
        plotter.add_mesh(slice_mesh, scalars=field, cmap="coolwarm", clim=(350, 352.2), lighting=False)
        plotter.add_axes()
        plotter.show_bounds()
        plotter.show()
        print(plotter.camera_position)
    elif args.mode == "2d":
        slice_mesh = mesh.slice(normal='x', origin=(0.0, 0.001609, 0.1))
        centers = slice_mesh.cell_centers().points
        y_coords = centers[:, 1]
        z_coords = centers[:, 2]
        temps = np.asarray(slice_mesh.cell_data[field])

        nbins_y = 200
        nbins_z = 200
        y_bins = np.linspace(y_coords.min(), y_coords.max(), nbins_y + 1)
        z_bins = np.linspace(z_coords.min(), z_coords.max(), nbins_z + 1)

        temp_grid, y_edges, z_edges = np.histogram2d(y_coords, z_coords, bins=[y_bins, z_bins], weights=temps)
        count_grid, _, _ = np.histogram2d(y_coords, z_coords, bins=[y_bins, z_bins])
        temp_grid = np.where(count_grid > 0, temp_grid / count_grid, np.nan)

        y_centers = (y_edges[:-1] + y_edges[1:]) / 2
        z_centers = (z_edges[:-1] + z_edges[1:]) / 2

        fig = go.Figure(data=go.Heatmap(
            x=y_centers,
            y=z_centers,
            z=temp_grid.T,
            colorscale='Viridis',
            colorbar=dict(title='Temperature / K'),
            hovertemplate='Y: %{x:.6f}<br>Z: %{y:.3f}<br>T: %{z:.2f} K<extra></extra>',
        ))
        fig.update_layout(
            xaxis_title='Y position / m',
            yaxis_title='Z position / m',
            width=600,
            height=800,
            margin=dict(l=80, r=40, t=40, b=80),
        )
        output_path = Path("slice_2d.html")
        fig.write_html(output_path)
        print(f"Written 2D heatmap to {output_path}")
        import webbrowser
        webbrowser.open(str(output_path.resolve()))
    else:
        slice_mesh = mesh.slice(normal='x', origin=(0.0, 0.001609, 0.1))
        slice_mesh = slice_mesh.triangulate().cell_data_to_point_data()
        faces = slice_mesh.faces
        i_arr = faces[1::4]
        j_arr = faces[2::4]
        k_arr = faces[3::4]

        fig = go.Figure(data=go.Mesh3d(
            x=slice_mesh.points[:, 0],
            y=slice_mesh.points[:, 1],
            z=slice_mesh.points[:, 2],
            i=i_arr,
            j=j_arr,
            k=k_arr,
            intensity=slice_mesh.point_data[field],
            colorscale='Viridis',
            colorbar={'title': 'Temperature / K'},
        ))
        fig.update_layout(scene=dict(
            xaxis_title='X',
            yaxis_title='Y',
            zaxis_title='Z',
            aspectmode='data',
            xaxis=dict(visible=False, showgrid=False, showline=False, zeroline=False, showticklabels=False, title=''),
            camera=dict(
                eye=dict(x=0.001, y=0, z=0.001),
                center=dict(x=0, y=0, z=0),
                up=dict(x=0, y=0, z=1)
            ),
        ))
        fig.to_plotly_json()
        print(f"Plotly Mesh3d created: {slice_mesh.n_points} points, {len(i_arr)} triangles")
        output_path = Path("slice_3d.html")
        fig.write_html(output_path)
        print(f"Written to {output_path}")
        import webbrowser
        webbrowser.open(str(output_path.resolve()))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
