"""
BUML-to-Canvas Parser — Converts BUML class descriptions from design.md
into the JSON format expected by the BESSER web editor canvas.

Handles layout computation to ensure classes are properly positioned.
"""

import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Layout constants
CLASS_WIDTH = 220
CLASS_HEIGHT_BASE = 80
ATTR_HEIGHT = 24
METHOD_HEIGHT = 24
PADDING_X = 80
PADDING_Y = 80
COLS = 3  # Number of columns in the grid layout


def generate_id() -> str:
    """Generate a UUID for canvas elements."""
    return str(uuid.uuid4())


def parse_design_to_canvas(design_content: str) -> dict:
    """Parse a design.md document and produce a canvas-compatible JSON.

    The JSON structure matches the BESSER web editor format with elements,
    relationships, and proper bounds/positioning.

    Args:
        design_content: The full text of design.md.

    Returns:
        A dict with the canvas JSON structure ready to load into the editor.
    """
    classes = _parse_classes(design_content)
    enumerations = _parse_enumerations(design_content)
    relationships = _parse_relationships(design_content)

    elements: dict[str, Any] = {}
    relationship_map: dict[str, Any] = {}
    class_id_map: dict[str, str] = {}  # class_name -> element_id

    # Layout: arrange classes in a grid
    all_items = classes + enumerations
    for idx, item in enumerate(all_items):
        col = idx % COLS
        row = idx // COLS

        item_name = item["name"]
        item_id = generate_id()
        class_id_map[item_name] = item_id

        # Calculate dynamic height based on number of attributes/methods
        attrs = item.get("attributes", [])
        methods = item.get("methods", [])
        literals = item.get("literals", [])

        num_children = len(attrs) + len(methods) + len(literals)
        item_height = CLASS_HEIGHT_BASE + num_children * ATTR_HEIGHT

        x = PADDING_X + col * (CLASS_WIDTH + PADDING_X)
        y = PADDING_Y + row * (item_height + PADDING_Y)

        bounds = {"x": x, "y": y, "width": CLASS_WIDTH, "height": item_height}

        if item.get("is_enum"):
            # Enumeration element
            attr_ids = []
            child_y = y + 40
            for lit in literals:
                lit_id = generate_id()
                elements[lit_id] = {
                    "id": lit_id,
                    "name": lit,
                    "type": "ClassAttribute",
                    "owner": item_id,
                    "bounds": {
                        "x": x,
                        "y": child_y,
                        "width": CLASS_WIDTH,
                        "height": ATTR_HEIGHT,
                    },
                }
                attr_ids.append(lit_id)
                child_y += ATTR_HEIGHT

            elements[item_id] = {
                "id": item_id,
                "name": item_name,
                "type": "Enumeration",
                "owner": None,
                "bounds": bounds,
                "attributes": attr_ids,
                "methods": [],
            }
        else:
            # Class element
            is_abstract = item.get("is_abstract", False)
            attr_ids = []
            method_ids = []

            child_y = y + 40

            for attr in attrs:
                attr_id = generate_id()
                # Determine visibility prefix
                vis = attr.get("visibility", "+")
                attr_type = attr.get("type", "str")
                attr_name_full = f"{vis} {attr['name']}: {attr_type}"

                elements[attr_id] = {
                    "id": attr_id,
                    "name": attr_name_full,
                    "type": "ClassAttribute",
                    "owner": item_id,
                    "bounds": {
                        "x": x,
                        "y": child_y,
                        "width": CLASS_WIDTH,
                        "height": ATTR_HEIGHT,
                    },
                    "visibility": _vis_name(vis),
                    "attributeType": attr_type,
                }
                attr_ids.append(attr_id)
                child_y += ATTR_HEIGHT

            for method in methods:
                method_id = generate_id()
                vis = method.get("visibility", "+")
                params_str = ", ".join(
                    f"{p['name']}: {p.get('type', 'any')}" for p in method.get("params", [])
                )
                ret = method.get("return_type", "")
                method_name_full = f"{vis} {method['name']}({params_str})"
                if ret:
                    method_name_full += f": {ret}"

                elements[method_id] = {
                    "id": method_id,
                    "name": method_name_full,
                    "type": "ClassMethod",
                    "owner": item_id,
                    "bounds": {
                        "x": x,
                        "y": child_y,
                        "width": CLASS_WIDTH,
                        "height": METHOD_HEIGHT,
                    },
                }
                method_ids.append(method_id)
                child_y += METHOD_HEIGHT

            elements[item_id] = {
                "id": item_id,
                "name": item_name,
                "type": "AbstractClass" if is_abstract else "Class",
                "owner": None,
                "bounds": bounds,
                "attributes": attr_ids,
                "methods": method_ids,
            }

    # Process relationships
    for rel in relationships:
        source_name = rel.get("source")
        target_name = rel.get("target")

        source_id = class_id_map.get(source_name)
        target_id = class_id_map.get(target_name)

        if not source_id or not target_id:
            logger.warning(
                f"[BUMLParser] Skipping relationship {source_name} -> {target_name}: "
                f"class not found in diagram."
            )
            continue

        rel_id = generate_id()
        rel_type = _map_relationship_type(rel.get("type", "Bidirectional"))

        source_elem = elements.get(source_id, {})
        target_elem = elements.get(target_id, {})

        source_bounds = source_elem.get("bounds", {"x": 0, "y": 0, "width": 200, "height": 100})
        target_bounds = target_elem.get("bounds", {"x": 0, "y": 0, "width": 200, "height": 100})

        # Calculate path for the relationship line
        source_center_x = source_bounds["x"] + source_bounds["width"] / 2
        source_center_y = source_bounds["y"] + source_bounds["height"] / 2
        target_center_x = target_bounds["x"] + target_bounds["width"] / 2
        target_center_y = target_bounds["y"] + target_bounds["height"] / 2

        relationship_map[rel_id] = {
            "id": rel_id,
            "name": rel.get("name", ""),
            "type": rel_type,
            "owner": None,
            "bounds": {
                "x": min(source_center_x, target_center_x),
                "y": min(source_center_y, target_center_y),
                "width": abs(target_center_x - source_center_x) or 1,
                "height": abs(target_center_y - source_center_y) or 1,
            },
            "path": [
                {"x": source_center_x, "y": source_center_y},
                {"x": target_center_x, "y": target_center_y},
            ],
            "source": {
                "element": source_id,
                "multiplicity": rel.get("source_mult", "1"),
                "role": rel.get("source_role", ""),
                "direction": _compute_direction(source_bounds, target_bounds),
                "bounds": {"x": source_center_x - 5, "y": source_center_y - 5, "width": 10, "height": 10},
            },
            "target": {
                "element": target_id,
                "multiplicity": rel.get("target_mult", "1"),
                "role": rel.get("target_role", ""),
                "direction": _compute_direction(target_bounds, source_bounds),
                "bounds": {"x": target_center_x - 5, "y": target_center_y - 5, "width": 10, "height": 10},
            },
        }

    # Assemble the final canvas JSON
    canvas_json = {
        "version": "3.0.0",
        "type": "ClassDiagram",
        "size": {"width": 2400, "height": 1600},
        "interactive": {"elements": {}, "relationships": {}},
        "elements": elements,
        "relationships": relationship_map,
        "assessments": {},
    }

    logger.info(
        f"[BUMLParser] Generated canvas with {len(class_id_map)} classes/enums, "
        f"{len(relationship_map)} relationships."
    )
    return canvas_json


def _parse_classes(content: str) -> list[dict]:
    """Parse class definitions from design.md content."""
    classes = []
    lines = content.split("\n")
    i = 0
    in_classes_section = False

    while i < len(lines):
        line = lines[i].strip()

        # Detect "### Classes" section
        if line.lower() == "### classes":
            in_classes_section = True
            i += 1
            continue

        # Detect "### Relationships" to stop parsing classes
        if line.lower() == "### relationships":
            in_classes_section = False
            i += 1
            continue

        if in_classes_section and line.startswith("#### "):
            class_name = line.replace("####", "").strip()
            cls: dict = {"name": class_name, "attributes": [], "methods": [], "is_abstract": False, "is_enum": False}
            i += 1

            while i < len(lines):
                cline = lines[i].strip()

                if cline.startswith("#### ") or cline.startswith("### ") or cline.startswith("## "):
                    break

                if cline.startswith("- **Type:**"):
                    type_val = cline.replace("- **Type:**", "").strip()
                    if type_val.lower() == "enumeration":
                        cls["is_enum"] = True
                elif cline.startswith("- **Abstract:**"):
                    abs_val = cline.replace("- **Abstract:**", "").strip().lower()
                    cls["is_abstract"] = abs_val in ("true", "yes")
                elif cline.startswith("- **Attributes:**"):
                    i += 1
                    while i < len(lines):
                        aline = lines[i].strip()
                        if not aline.startswith("- "):
                            break
                        attr = _parse_attribute_line(aline)
                        if attr:
                            cls["attributes"].append(attr)
                        i += 1
                    continue
                elif cline.startswith("- **Methods:**"):
                    i += 1
                    while i < len(lines):
                        mline = lines[i].strip()
                        if not mline.startswith("- "):
                            break
                        method = _parse_method_line(mline)
                        if method:
                            cls["methods"].append(method)
                        i += 1
                    continue
                elif cline.startswith("- **Literals:**"):
                    cls["is_enum"] = True
                    cls["literals"] = []
                    i += 1
                    while i < len(lines):
                        lline = lines[i].strip()
                        if not lline.startswith("- "):
                            break
                        literal = lline.lstrip("- ").strip()
                        if literal:
                            cls["literals"].append(literal)
                        i += 1
                    continue

                i += 1

            classes.append(cls)
            continue

        i += 1

    return classes


def _parse_enumerations(content: str) -> list[dict]:
    """Parse enumeration definitions (already handled in _parse_classes with is_enum flag)."""
    # Enumerations are parsed as part of _parse_classes with is_enum=True
    return []


def _parse_relationships(content: str) -> list[dict]:
    """Parse relationship definitions from design.md content."""
    relationships = []
    lines = content.split("\n")
    i = 0
    in_relationships_section = False

    while i < len(lines):
        line = lines[i].strip()

        if line.lower() == "### relationships":
            in_relationships_section = True
            i += 1
            continue

        if in_relationships_section and (line.startswith("## ") and not line.startswith("### ")):
            break

        if in_relationships_section and line.startswith("#### "):
            # Parse relationship header: "#### ClassName1 → ClassName2"
            header = line.replace("####", "").strip()
            # Handle various arrow formats
            parts = None
            for arrow in ["→", "->", "—>", "=>", " to "]:
                if arrow in header:
                    parts = [p.strip() for p in header.split(arrow, 1)]
                    break

            if not parts or len(parts) != 2:
                i += 1
                continue

            rel: dict = {
                "source": parts[0],
                "target": parts[1],
                "type": "Bidirectional",
                "source_mult": "1",
                "target_mult": "1",
                "source_role": "",
                "target_role": "",
                "name": "",
            }

            i += 1
            while i < len(lines):
                rline = lines[i].strip()
                if rline.startswith("#### ") or rline.startswith("### ") or rline.startswith("## "):
                    break

                if rline.startswith("- **Type:**"):
                    rel["type"] = rline.replace("- **Type:**", "").strip()
                elif rline.startswith("- **Source Multiplicity:**"):
                    rel["source_mult"] = rline.replace("- **Source Multiplicity:**", "").strip()
                elif rline.startswith("- **Target Multiplicity:**"):
                    rel["target_mult"] = rline.replace("- **Target Multiplicity:**", "").strip()
                elif rline.startswith("- **Source Role:**"):
                    rel["source_role"] = rline.replace("- **Source Role:**", "").strip()
                elif rline.startswith("- **Target Role:**"):
                    rel["target_role"] = rline.replace("- **Target Role:**", "").strip()

                i += 1

            relationships.append(rel)
            continue

        i += 1

    return relationships


def _parse_attribute_line(line: str) -> dict | None:
    """Parse an attribute line like '- + name: str' or '- # age: int'."""
    text = line.lstrip("- ").strip()
    if not text:
        return None

    vis = "+"
    if text[0] in ("+", "-", "#"):
        vis = text[0]
        text = text[1:].strip()

    # Parse "name: type" or just "name"
    if ":" in text:
        parts = text.split(":", 1)
        name = parts[0].strip()
        attr_type = parts[1].strip()
    else:
        name = text.strip()
        attr_type = "str"

    if not name:
        return None

    return {"name": name, "type": attr_type, "visibility": vis}


def _parse_method_line(line: str) -> dict | None:
    """Parse a method line like '- + calculate_total(items: list): float'."""
    text = line.lstrip("- ").strip()
    if not text:
        return None

    vis = "+"
    if text[0] in ("+", "-", "#"):
        vis = text[0]
        text = text[1:].strip()

    # Try to parse "name(params): returnType"
    paren_open = text.find("(")
    paren_close = text.find(")")

    if paren_open == -1:
        # No parentheses — treat as a method with no params
        name = text.split(":")[0].strip() if ":" in text else text.strip()
        ret = text.split(":")[-1].strip() if ":" in text else ""
        return {"name": name, "params": [], "return_type": ret, "visibility": vis}

    name = text[:paren_open].strip()
    params_text = text[paren_open + 1:paren_close].strip() if paren_close > paren_open else ""
    rest = text[paren_close + 1:].strip() if paren_close < len(text) else ""

    ret = ""
    if rest.startswith(":"):
        ret = rest[1:].strip()

    params = []
    if params_text:
        for param in params_text.split(","):
            param = param.strip()
            if ":" in param:
                pname, ptype = param.split(":", 1)
                params.append({"name": pname.strip(), "type": ptype.strip()})
            else:
                params.append({"name": param, "type": "any"})

    return {"name": name, "params": params, "return_type": ret, "visibility": vis}


def _map_relationship_type(rel_type: str) -> str:
    """Map design.md relationship type to canvas relationship type."""
    mapping = {
        "bidirectional": "ClassBidirectional",
        "unidirectional": "ClassUnidirectional",
        "composition": "ClassComposition",
        "aggregation": "ClassAggregation",
        "inheritance": "ClassInheritance",
        "generalization": "ClassInheritance",
        "realization": "ClassRealization",
        "dependency": "ClassDependency",
    }
    return mapping.get(rel_type.lower().strip(), "ClassBidirectional")


def _vis_name(symbol: str) -> str:
    """Convert visibility symbol to name."""
    return {"+" : "public", "-": "private", "#": "protected"}.get(symbol, "public")


def _compute_direction(from_bounds: dict, to_bounds: dict) -> str:
    """Compute the direction from one element to another for connector anchoring."""
    from_cx = from_bounds["x"] + from_bounds["width"] / 2
    from_cy = from_bounds["y"] + from_bounds["height"] / 2
    to_cx = to_bounds["x"] + to_bounds["width"] / 2
    to_cy = to_bounds["y"] + to_bounds["height"] / 2

    dx = to_cx - from_cx
    dy = to_cy - from_cy

    if abs(dx) > abs(dy):
        return "Right" if dx > 0 else "Left"
    else:
        return "Down" if dy > 0 else "Up"
