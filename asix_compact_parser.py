#!/usr/bin/env python3
"""
AVL FIRE ASIX (XML) -> Compact nested dict (Option A, compact form)

- XML tags become dict keys.
- Attributes are stored under a reserved key: "_attrs".
- Repeated sibling tags become lists; singletons remain dicts.
- Optional: cast "_attrs.value" using "_attrs.type".
- Optional: sort lists by numeric "_attrs.index" when all items have an index.

Example output shape (conceptual):

{
  "AST_input_data": {
    "_attrs": {... optional ...},
    "AST_information": {
      "host_name": {"_attrs": {"type": "string", "value": "zbta138"}},
      ...
    },
    "item": [
      {"_attrs": {"index": "0", ...}, ...},
      {"_attrs": {"index": "1", ...}, ...}
    ]
  }
}

Usage:
  python asix_compact_parser.py FIRE_M_1.asix
  python asix_compact_parser.py FIRE_M_1.asix --json asix_compact.json
  python asix_compact_parser.py FIRE_M_1.asix --cast --json asix_compact.json
  python asix_compact_parser.py FIRE_M_1.asix --always-list --json asix_compact.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from lxml import etree


REMAP_ATTRS = {"t": "type", "v": "value", "u": "unit"}
ATTRS_KEY = "_attrs"

INTERESTING_ATTRS = {
    "type",
    "value",
    "unit",
    "name",
    "index",
    "reference_id",
    "map_type",
    "data_type",
    "orientation",
}


def _local_tag(el: etree._Element) -> str:
    return etree.QName(el).localname


def _try_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(str(x))
    except Exception:
        return None


def _cast_value(type_str: Optional[str], raw: Any) -> Any:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    if not type_str:
        return raw

    t = type_str.strip().lower()
    if t == "string":
        return raw
    if t in {"int", "integer"}:
        try:
            return int(raw)
        except ValueError:
            return raw
    if t in {"double", "float", "real"}:
        try:
            return float(raw)
        except ValueError:
            return raw
    if t in {"bool", "boolean"}:
        return raw.strip().lower() in {"yes", "true", "1"}
    if t == "date":
        for fmt in ("%Y%m%d %H:%M:%S", "%Y%m%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                pass
        return raw
    return raw


def _sort_lists_by_index(obj: Any) -> None:
    """Recursively sort any list of dict-nodes by numeric _attrs.index when possible."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == ATTRS_KEY:
                continue
            _sort_lists_by_index(v)
        return

    if isinstance(obj, list):
        idxs = []
        for item in obj:
            if not isinstance(item, dict):
                idxs.append(None)
                continue
            attrs = item.get(ATTRS_KEY, {}) or {}
            idxs.append(_try_int(attrs.get("index")))

        if obj and all(i is not None for i in idxs):
            obj.sort(key=lambda it: _try_int(((it.get(ATTRS_KEY) or {}).get("index"))) or 0)

        for item in obj:
            _sort_lists_by_index(item)


def asix_to_compact_dict(
    root: etree._Element,
    *,
    always_list: bool = False,
    cast_values: bool = False,
    keep_all_attributes: bool = True,
) -> dict[str, Any]:
    """
    Convert ASIX XML root to compact nested dict.

    - always_list=False: singletons are dict; repeats are list
    - always_list=True: children[tag] always list
    - cast_values=True: cast _attrs.value using _attrs.type
    - keep_all_attributes=True: keep all attributes under _attrs (with t/v/u remapped)
    """

    def convert(el: etree._Element) -> dict[str, Any]:
        node: dict[str, Any] = {}

        # Attributes
        attrs: dict[str, Any] = {}
        for k, v in el.attrib.items():
            kk = REMAP_ATTRS.get(k, k)
            if keep_all_attributes or kk in INTERESTING_ATTRS:
                attrs[kk] = v

        if cast_values and "value" in attrs:
            attrs["value"] = _cast_value(attrs.get("type"), attrs.get("value"))

        if attrs:
            node[ATTRS_KEY] = attrs

        # Children grouped by tag
        groups: dict[str, list[dict[str, Any]]] = {}
        for child in el:
            if not isinstance(child.tag, str):  # skip comments/PIs
                continue
            tag = _local_tag(child)
            groups.setdefault(tag, []).append(convert(child))

        for tag, items in groups.items():
            node[tag] = items if always_list else (items[0] if len(items) == 1 else items)

        return node

    out = {_local_tag(root): convert(root)}
    _sort_lists_by_index(out)
    return out


def parse_asix(
    asix_path: Path,
    *,
    always_list: bool = False,
    cast_values: bool = False,
    keep_all_attributes: bool = True,
) -> dict[str, Any]:
    parser = etree.XMLParser(remove_comments=True, huge_tree=True)
    tree = etree.parse(str(asix_path), parser)
    root = tree.getroot()
    return asix_to_compact_dict(
        root,
        always_list=always_list,
        cast_values=cast_values,
        keep_all_attributes=keep_all_attributes,
    )


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse AVL FIRE .asix into a compact nested dict (tags as keys).")
    ap.add_argument("asix", type=Path, help="Path to .asix file")
    ap.add_argument("--json", type=Path, default=None, help="Write output to JSON file")
    ap.add_argument("--always-list", action="store_true", help="Force children[tag] to always be a list")
    ap.add_argument("--cast", action="store_true", help="Cast _attrs.value using _attrs.type when possible")
    ap.add_argument(
        "--keep-interesting-only",
        action="store_true",
        help="Keep only key attributes (type/value/unit/name/index/reference_id/map_type/data_type/orientation) under _attrs",
    )

    args = ap.parse_args()
    if not args.asix.exists():
        raise SystemExit(f"File not found: {args.asix}")

    out = parse_asix(
        args.asix,
        always_list=args.always_list,
        cast_values=args.cast,
        keep_all_attributes=not args.keep_interesting_only,
    )

    root_tag = next(iter(out.keys()))
    top_keys = list((out[root_tag] or {}).keys())
    print(f"Parsed: {args.asix.name}")
    print(f"Root tag: {root_tag}")
    print(f"Top-level keys under root (first 30): {top_keys[:30]}")

    if args.json:
        args.json.write_text(
            json.dumps(out, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        print(f"Wrote JSON: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
