from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


DEFAULT_IGNORED_PREFIXES = (
    "AST_input_data.AST_information",
    "AST_input_data.simfs_paths",
)


def load_config() -> dict[str, Any]:
    load_dotenv()

    model_name = os.getenv("MODEL_NAME")
    case_set_names = [cs.strip() for cs in os.getenv("CASE_SET_NAME", "").split(",") if cs.strip()]
    case_name = os.getenv("CASE_NAME")
    if case_name == "None":
        case_name = None

    missing = [
        name
        for name, value in {
            "MODEL_NAME": model_name,
            "CASE_SET_NAME": case_set_names,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return {
        "model_name": model_name,
        "case_set_names": case_set_names,
        "case_name": case_name,
    }


def parse_args() -> argparse.Namespace:
    config = load_config()

    parser = argparse.ArgumentParser(
        description="Compare local input.json files across case sets and print only differing parameters."
    )
    parser.add_argument("--model-name", default=config["model_name"])
    parser.add_argument("--case-sets", nargs="+", default=config["case_set_names"])
    parser.add_argument("--case-name", default=config["case_name"])
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="Root directory containing the local model/case-set/case folders.",
    )
    parser.add_argument(
        "--include-metadata",
        action="store_true",
        help="Include AST metadata and simfs paths in the comparison.",
    )
    parser.add_argument(
        "--show-missing-cases",
        action="store_true",
        help="Report cases that are not present in every selected case set.",
    )
    return parser.parse_args()


def flatten_json(node: Any, path: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            flat.update(flatten_json(value, child_path))
        return flat

    if isinstance(node, list):
        for index, value in enumerate(node):
            child_path = f"{path}[{index}]"
            flat.update(flatten_json(value, child_path))
        return flat

    flat[path] = node
    return flat


def should_ignore(path: str, include_metadata: bool) -> bool:
    if include_metadata:
        return False
    return any(path.startswith(prefix) for prefix in DEFAULT_IGNORED_PREFIXES)


def value_signature(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


def load_case_inputs(
    data_root: Path,
    model_name: str,
    case_set_names: list[str],
    requested_case_name: str | None,
) -> dict[str, dict[str, Path]]:
    case_map: dict[str, dict[str, Path]] = defaultdict(dict)

    for case_set_name in case_set_names:
        case_set_dir = data_root / model_name / case_set_name
        if not case_set_dir.exists():
            raise FileNotFoundError(f"Case set directory not found: {case_set_dir}")

        if requested_case_name is not None:
            case_dir = case_set_dir / requested_case_name
            input_path = case_dir / "input.json"
            if input_path.exists():
                case_map[requested_case_name][case_set_name] = input_path
            continue

        for case_dir in sorted(path for path in case_set_dir.iterdir() if path.is_dir()):
            input_path = case_dir / "input.json"
            if input_path.exists():
                case_map[case_dir.name][case_set_name] = input_path

    return dict(case_map)


def compare_case_group(case_paths: dict[str, Path], include_metadata: bool) -> list[tuple[str, dict[str, Any]]]:
    flattened_by_case_set: dict[str, dict[str, Any]] = {}
    for case_set_name, input_path in case_paths.items():
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        flattened = flatten_json(payload)
        filtered = {
            path: value
            for path, value in flattened.items()
            if not should_ignore(path, include_metadata)
        }
        flattened_by_case_set[case_set_name] = filtered

    all_paths = sorted(set().union(*(flat.keys() for flat in flattened_by_case_set.values())))
    differences: list[tuple[str, dict[str, Any]]] = []
    for path in all_paths:
        values = {
            case_set_name: flattened_by_case_set[case_set_name].get(path, "<missing>")
            for case_set_name in sorted(flattened_by_case_set)
        }
        if len({value_signature(value) for value in values.values()}) > 1:
            differences.append((path, values))
    return differences


def print_report(
    case_map: dict[str, dict[str, Path]],
    model_name: str,
    case_set_names: list[str],
    include_metadata: bool,
    show_missing_cases: bool,
) -> None:
    expected_case_sets = set(case_set_names)
    matching_cases = sorted(
        case_name
        for case_name, case_paths in case_map.items()
        if set(case_paths) == expected_case_sets
    )
    missing_cases = sorted(
        case_name
        for case_name, case_paths in case_map.items()
        if set(case_paths) != expected_case_sets
    )

    print(f"Model: {model_name}")
    print(f"Case sets: {', '.join(case_set_names)}")
    print(f"Metadata included: {'yes' if include_metadata else 'no'}")
    print()

    if show_missing_cases and missing_cases:
        print("Cases missing in at least one case set:")
        for case_name in missing_cases:
            present = ", ".join(sorted(case_map[case_name]))
            print(f"- {case_name}: present in {present}")
        print()

    if not matching_cases:
        print("No cases were found in all selected case sets.")
        return

    total_differences = 0
    for case_name in matching_cases:
        differences = compare_case_group(case_map[case_name], include_metadata)
        if not differences:
            continue

        total_differences += len(differences)
        print(case_name)
        for path, values in differences:
            print(f"  {path}")
            for case_set_name in case_set_names:
                value = values[case_set_name]
                print(f"    {case_set_name}: {value!r}")
        print()

    if total_differences == 0:
        print("No differing input parameters were found across the selected case sets.")


if __name__ == "__main__":
    args = parse_args()
    case_map = load_case_inputs(
        data_root=args.data_root,
        model_name=args.model_name,
        case_set_names=args.case_sets,
        requested_case_name=args.case_name,
    )
    print_report(
        case_map=case_map,
        model_name=args.model_name,
        case_set_names=args.case_sets,
        include_metadata=args.include_metadata,
        show_missing_cases=args.show_missing_cases,
    )
