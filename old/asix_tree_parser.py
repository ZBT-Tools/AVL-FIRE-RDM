#!/usr/bin/env python3
"""
AVL FIRE ASIX (XML) -> Tree-first Python dict (Option A)

Representation ("node object"):
{
  "tag": "<element-tag>",
  "attrs": {
      "type": ...,        # from XML attribute t
      "value": ...,       # from XML attribute v
      "unit": ...,        # from XML attribute u
      "name": ...,
      "index": ...,
      "reference_id": ...,
      "map_type": ...,
      "data_type": ...,
      "orientation": ...,
      ...
  },
  "attrs_extra": {...},  # optional, any other attributes not captured above
  "children": {
      "<child-tag>": <node> OR [<node>, <node>, ...]    # depending on repeats / always_list
  }
}

Key behaviors:
- Children are grouped by tag (Option A)
- Repeated tags become lists
- Optional: force every child entry to be a list via --always-list
- Optional: type-cast values based on "type" via --cast
- Lists are sorted by numeric "index" when all elements have an index

Usage examples:
  python asix_tree_parser.py FIRE_M_1.asix
  python asix_tree_parser.py FIRE_M_1.asix --json out.json
  python asix_tree_parser.py FIRE_M_1.asix --always-list --cast --json out.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from lxml import etree


KEEP_ATTRS = {
    "name",
    "index",
    "reference_id",
    "map_type",
    "data_type",
    "orientation",
}

REMAP_ATTRS = {
    "t": "type",
    "v": "value",
    "u": "unit",
}


def _cast_value(type_str: Optional[str], raw: Any) -> Any:
    """
    Cast the ASIX 'value' according to ASIX 'type'.
    If casting fails or type is unknown, returns the raw string.
    """
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


def _local_tag(el: etree._Element) -> str:
    return etree.QName(el).localname


def _try_int(s: Any) -> Optional[int]:
    if s is None:
        return None
    try:
        return int(str(s))
    except Exception:
        return None


def _sort_children_lists(node: dict) -> None:
    """
    Recursively sort lists under node["children"] by numeric attrs.index when possible.
    """
    children = node.get("children") or {}
    for v in children.values():
        if isinstance(v, list):
            idxs = [_try_int((child.get("attrs") or {}).get("index")) for child in v]
            if all(i is not None for i in idxs):
                v.sort(key=lambda child: _try_int((child.get("attrs") or {}).get("index")) or 0)
            for child in v:
                _sort_children_lists(child)
        elif isinstance(v, dict):
            _sort_children_lists(v)


def build_tree(
    root: etree._Element,
    *,
    always_list: bool = False,
    keep_extra_attrs: bool = True,
    cast_values: bool = False,
) -> dict:
    """
    Convert an lxml element into the Option A tree-first structure.
    """

    def convert(el: etree._Element) -> dict:
        node: dict = {"tag": _local_tag(el), "attrs": {}, "children": {}}

        attrs: dict = {}
        extra: dict = {}

        for k, v in el.attrib.items():
            if k in REMAP_ATTRS:
                attrs[REMAP_ATTRS[k]] = v
            elif k in KEEP_ATTRS:
                attrs[k] = v
            else:
                if keep_extra_attrs:
                    extra[k] = v

        if cast_values and "value" in attrs:
            attrs["value"] = _cast_value(attrs.get("type"), attrs.get("value"))

        node["attrs"] = attrs
        if keep_extra_attrs and extra:
            node["attrs_extra"] = extra

        # Children grouped by tag
        for child in el:
            if not isinstance(child.tag, str):
                continue
            ctag = _local_tag(child)
            cnode = convert(child)

            if ctag not in node["children"]:
                node["children"][ctag] = [cnode] if always_list else cnode
            else:
                existing = node["children"][ctag]
                if isinstance(existing, list):
                    existing.append(cnode)
                else:
                    node["children"][ctag] = [existing, cnode]

        return node

    out = convert(root)
    _sort_children_lists(out)
    return out


def parse_asix(
    asix_path: Path,
    *,
    always_list: bool = False,
    keep_extra_attrs: bool = True,
    cast_values: bool = False,
) -> dict:
    parser = etree.XMLParser(remove_comments=True, huge_tree=True)
    tree = etree.parse(str(asix_path), parser)
    root = tree.getroot()
    return build_tree(root, always_list=always_list, keep_extra_attrs=keep_extra_attrs, cast_values=cast_values)


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _count_nodes(node: dict) -> int:
    n = 1
    children = node.get("children") or {}
    for v in children.values():
        if isinstance(v, list):
            for ch in v:
                n += _count_nodes(ch)
        elif isinstance(v, dict):
            n += _count_nodes(v)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse AVL FIRE .asix into a tree-first dict (Option A).")
    ap.add_argument("asix", type=Path, help="Path to .asix file")
    ap.add_argument("--json", type=Path, default=None, help="Write output to JSON file")
    ap.add_argument("--always-list", action="store_true", help="Force children[tag] to always be a list")
    ap.add_argument("--no-extra-attrs", action="store_true", help="Do not keep non-standard attributes")
    ap.add_argument("--cast", action="store_true", help="Cast attrs.value using attrs.type when possible")

    args = ap.parse_args()

    if not args.asix.exists():
        raise SystemExit(f"File not found: {args.asix}")

    tree_dict = parse_asix(
        args.asix,
        always_list=args.always_list,
        keep_extra_attrs=not args.no_extra_attrs,
        cast_values=args.cast,
    )

    total = _count_nodes(tree_dict)
    print(f"Parsed: {args.asix.name}")
    print(f"Total nodes: {total}")
    print(f"Root tag: {tree_dict.get('tag')}")
    print(f"Root child tags (first 20): {list((tree_dict.get('children') or {}).keys())[:20]}")

    if args.json:
        args.json.write_text(
            json.dumps(tree_dict, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        print(f"Wrote JSON: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
