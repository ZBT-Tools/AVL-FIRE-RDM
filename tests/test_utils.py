from src import utils


def test_read_ensight_case_definition_extracts_time_and_variable_paths():
    case_text = """FORMAT
type: ensight gold
GEOMETRY
model: 1 demo.geo
VARIABLE
scalar per element: 1 Temperature ********/demo_temperature.var
vector per element: 1 Velocity ********/demo_velocity.var
TIME
time set: 1
number of steps: 4
filename start number: 1
filename increment: 2
time values:
0.0
1.0
"""
    case_definition = utils._read_ensight_case_definition(case_text)

    assert case_definition["geometry_model"] == "demo.geo"
    assert case_definition["variable_relative_paths"] == [
        "********/demo_temperature.var",
        "********/demo_velocity.var",
    ]
    assert case_definition["number_of_steps"] == 4
    assert case_definition["filename_start_number"] == 1
    assert case_definition["filename_increment"] == 2
    assert utils._last_ensight_step_number(case_definition) == 7


def test_resolve_ensight_relative_path_for_step_replaces_wildcard():
    resolved = utils._resolve_ensight_relative_path_for_step(
        "********/demo_temperature.var",
        7,
    )

    assert resolved == "00000007/demo_temperature.var"
