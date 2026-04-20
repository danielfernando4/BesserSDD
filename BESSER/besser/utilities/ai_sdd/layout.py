"""
Layout Engine for BESSER Class Diagrams — Independent of BESSER libraries.

Takes a SystemClassSpec-style dict (classes + relationships) and assigns
position: {x, y} to each class using a relationship-aware grid algorithm.

Design principles:
 - Inheritance places parent above children (vertical hierarchy).
 - Associations are placed horizontally when possible.
 - Compositions place the whole above its parts.
 - Collision-free positioning with grid snapping.
 - Canvas centered at (0, 0) matching the BESSER web editor.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Sizing constants (match BESSER web editor) ─────────────────────────

CLASS_WIDTH = 220
CLASS_HEADER_HEIGHT = 50
CLASS_ATTR_ROW = 25
CLASS_METHOD_ROW = 25
CLASS_MIN_HEIGHT = 90

H_GAP = 60
V_GAP = 60
GRID_SNAP = 20


def _snap(value: int) -> int:
    """Snap a coordinate to the nearest grid multiple."""
    return round(value / GRID_SNAP) * GRID_SNAP


def estimate_class_size(cls: Dict[str, Any]) -> Tuple[int, int]:
    """Return (width, height) for a class spec."""
    n_attrs = len(cls.get("attributes", []))
    n_methods = len(cls.get("methods", []))
    height = CLASS_HEADER_HEIGHT + n_attrs * CLASS_ATTR_ROW + n_methods * CLASS_METHOD_ROW
    return CLASS_WIDTH, max(height, CLASS_MIN_HEIGHT)


# ── Graph building ─────────────────────────────────────────────────────

def _build_graph(
    class_names: List[str],
    relationships: List[Dict[str, Any]],
) -> Tuple[Dict[str, Set[str]], Dict[str, str], Dict[str, Set[str]]]:
    """Build adjacency, parent_of, and children_of from relationships.
    
    Returns:
        adjacency: undirected adjacency dict
        parent_of: child -> parent (for inheritance)
        children_of: parent -> set of children
    """
    adjacency: Dict[str, Set[str]] = {name: set() for name in class_names}
    parent_of: Dict[str, str] = {}
    children_of: Dict[str, Set[str]] = defaultdict(set)
    
    name_set = set(class_names)
    
    for rel in relationships:
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        rtype = (rel.get("type") or "").lower()
        
        if src not in name_set or tgt not in name_set or src == tgt:
            continue
        
        adjacency.setdefault(src, set()).add(tgt)
        adjacency.setdefault(tgt, set()).add(src)
        
        if rtype in ("inheritance", "generalization"):
            # source = child, target = parent
            parent_of[src] = tgt
            children_of[tgt].add(src)
        elif rtype in ("composition", "aggregation"):
            # source = whole, target = part → treat whole as parent
            if tgt not in parent_of:
                parent_of[tgt] = src
                children_of[src].add(tgt)
    
    return adjacency, parent_of, children_of


def _find_roots(
    class_names: List[str],
    parent_of: Dict[str, str],
    adjacency: Dict[str, Set[str]],
) -> List[str]:
    """Find root nodes: inheritance roots first, then by degree."""
    roots = []
    non_roots = set(parent_of.keys())
    
    # Inheritance roots (parents that are not children of anyone)
    for name in class_names:
        if name not in non_roots and any(
            parent_of.get(child) == name
            for child in class_names
        ):
            roots.append(name)
    
    # Remaining unplaced nodes sorted by degree (most connected first)
    remaining = [n for n in class_names if n not in roots and n not in non_roots]
    remaining.sort(key=lambda n: len(adjacency.get(n, set())), reverse=True)
    
    return roots + remaining


# ── Grid assignment ────────────────────────────────────────────────────

def _assign_grid(
    class_names: List[str],
    relationships: List[Dict[str, Any]],
) -> Dict[str, Tuple[int, int]]:
    """Assign logical (row, col) grid positions to classes.
    
    Strategy:
    - Roots go in row 0
    - Children of each root go in row 1, 2, ... (BFS)
    - Unconnected classes fill remaining grid positions
    """
    adjacency, parent_of, children_of = _build_graph(class_names, relationships)
    roots = _find_roots(class_names, parent_of, adjacency)
    
    grid: Dict[str, Tuple[int, int]] = {}
    placed: Set[str] = set()
    
    col_counter = 0
    
    # Phase 1: Place inheritance trees (BFS from roots)
    for root in roots:
        if root in placed:
            continue
        
        # BFS to place the tree rooted at this node
        queue = [(root, 0)]  # (name, depth)
        tree_nodes: List[Tuple[str, int]] = []
        
        while queue:
            node, depth = queue.pop(0)
            if node in placed:
                continue
            tree_nodes.append((node, depth))
            placed.add(node)
            
            # Add children (inheritance + composition)
            for child in sorted(children_of.get(node, set())):
                if child not in placed:
                    queue.append((child, depth + 1))
        
        if not tree_nodes:
            continue
        
        # Assign grid positions: the root at (0, col_counter)
        # Children spread horizontally below
        depth_groups: Dict[int, List[str]] = defaultdict(list)
        for name, depth in tree_nodes:
            depth_groups[depth].append(name)
        
        # Calculate width needed for deepest level
        max_width = max(len(names) for names in depth_groups.values())
        start_col = col_counter
        
        for depth in sorted(depth_groups.keys()):
            names = depth_groups[depth]
            # Center children under parent
            offset = (max_width - len(names)) // 2
            for i, name in enumerate(names):
                grid[name] = (depth, start_col + offset + i)
        
        col_counter = start_col + max_width  # no gap columns between trees
    
    # Phase 2: Place unconnected classes in a multi-row grid (max 3 cols)
    unplaced = [n for n in class_names if n not in placed]
    if unplaced:
        # Find the max row and max col used
        max_row_used = max((r for r, _ in grid.values()), default=-1)
        max_col_used = max((c for _, c in grid.values()), default=-1)
        # Place beside existing content (not leaving huge gaps)
        start_col = max_col_used + 1 if grid else 0
        target_row = 0  # Start from top row
        max_cols = 3
        for i, name in enumerate(unplaced):
            row = target_row + i // max_cols
            col = start_col + (i % max_cols)
            grid[name] = (row, col)
    
    # ── Normalize: compact sparse columns into sequential 0,1,2,... ──
    if grid:
        used_cols = sorted(set(c for _, c in grid.values()))
        col_remap = {old: new for new, old in enumerate(used_cols)}
        grid = {name: (r, col_remap[c]) for name, (r, c) in grid.items()}
    
    return grid


# ── Grid → Pixel conversion ───────────────────────────────────────────

def _grid_to_pixels(
    grid: Dict[str, Tuple[int, int]],
    sizes: Dict[str, Tuple[int, int]],
) -> Dict[str, Dict[str, int]]:
    """Convert logical grid positions to pixel coordinates centered at origin."""
    if not grid:
        return {}
    
    min_row = min(r for r, _ in grid.values())
    max_row = max(r for r, _ in grid.values())
    min_col = min(c for _, c in grid.values())
    max_col = max(c for _, c in grid.values())
    
    # Calculate per-column width and per-row height
    col_widths: Dict[int, int] = {}
    row_heights: Dict[int, int] = {}
    
    for name, (r, c) in grid.items():
        w, h = sizes.get(name, (CLASS_WIDTH, CLASS_MIN_HEIGHT))
        col_widths[c] = max(col_widths.get(c, 0), w)
        row_heights[r] = max(row_heights.get(r, 0), h)
    
    # Total layout dimensions
    total_width = sum(col_widths.get(c, CLASS_WIDTH) for c in range(min_col, max_col + 1))
    total_width += H_GAP * max(0, (max_col - min_col))
    
    total_height = sum(row_heights.get(r, CLASS_MIN_HEIGHT) for r in range(min_row, max_row + 1))
    total_height += V_GAP * max(0, (max_row - min_row))
    
    # Calculate dynamic origin to center the diagram near (-250, -200)
    # which is the sweet spot of the visible canvas viewport.
    target_cx = -250
    target_cy = -200
    origin_x = _snap(target_cx - total_width // 2)
    origin_y = _snap(target_cy - total_height // 2)
    
    positions: Dict[str, Dict[str, int]] = {}
    
    for name, (r, c) in grid.items():
        w, h = sizes.get(name, (CLASS_WIDTH, CLASS_MIN_HEIGHT))
        
        # X: sum of column widths + gaps
        px = origin_x
        for cc in range(min_col, c):
            px += col_widths.get(cc, CLASS_WIDTH) + H_GAP
        # Center in column
        px += (col_widths.get(c, CLASS_WIDTH) - w) // 2
        
        # Y: sum of row heights + gaps
        py = origin_y
        for rr in range(min_row, r):
            py += row_heights.get(rr, CLASS_MIN_HEIGHT) + V_GAP
        # Center in row
        py += (row_heights.get(r, CLASS_MIN_HEIGHT) - h) // 2
        
        positions[name] = {"x": _snap(px), "y": _snap(py)}
    
    return positions


# ── Edge direction computation ─────────────────────────────────────────

def _compute_directions(
    relationships: List[Dict[str, Any]],
    positions: Dict[str, Dict[str, int]],
    sizes: Dict[str, Tuple[int, int]],
) -> None:
    """Compute sourceDirection/targetDirection for each relationship (mutates in-place)."""
    for rel in relationships:
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        
        src_pos = positions.get(src)
        tgt_pos = positions.get(tgt)
        if not src_pos or not tgt_pos:
            continue
        
        src_w, src_h = sizes.get(src, (CLASS_WIDTH, CLASS_MIN_HEIGHT))
        tgt_w, tgt_h = sizes.get(tgt, (CLASS_WIDTH, CLASS_MIN_HEIGHT))
        
        src_cx = src_pos["x"] + src_w / 2
        src_cy = src_pos["y"] + src_h / 2
        tgt_cx = tgt_pos["x"] + tgt_w / 2
        tgt_cy = tgt_pos["y"] + tgt_h / 2
        
        dx = tgt_cx - src_cx
        dy = tgt_cy - src_cy
        
        rtype = (rel.get("type") or "").lower()
        if rtype in ("inheritance", "generalization"):
            if dy < 0:
                rel["sourceDirection"] = "Up"
                rel["targetDirection"] = "Down"
            else:
                rel["sourceDirection"] = "Down"
                rel["targetDirection"] = "Up"
        else:
            if abs(dx) >= abs(dy):
                if dx >= 0:
                    rel["sourceDirection"] = "Right"
                    rel["targetDirection"] = "Left"
                else:
                    rel["sourceDirection"] = "Left"
                    rel["targetDirection"] = "Right"
            else:
                if dy >= 0:
                    rel["sourceDirection"] = "Down"
                    rel["targetDirection"] = "Up"
                else:
                    rel["sourceDirection"] = "Up"
                    rel["targetDirection"] = "Down"


# ── Public API ─────────────────────────────────────────────────────────

def apply_layout(system_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Apply relationship-aware layout to a SystemClassSpec.
    
    Mutates each class in `system_spec["classes"]` by adding
    `position: {x, y}` and sets `sourceDirection`/`targetDirection`
    on each relationship.
    
    Args:
        system_spec: Dict with keys `classes` (list) and `relationships` (list).
    
    Returns:
        The same dict, mutated with positions.
    """
    classes = system_spec.get("classes", [])
    relationships = system_spec.get("relationships", [])
    
    if not classes:
        return system_spec
    
    # Build name → class lookup
    class_lookup: Dict[str, Dict[str, Any]] = {}
    class_names: List[str] = []
    for cls in classes:
        name = cls.get("className", "")
        if name:
            class_lookup[name] = cls
            class_names.append(name)
    
    # Estimate sizes
    sizes: Dict[str, Tuple[int, int]] = {}
    for name, cls in class_lookup.items():
        sizes[name] = estimate_class_size(cls)
    
    # Assign grid positions
    grid = _assign_grid(class_names, relationships)
    
    # Convert to pixel positions
    positions = _grid_to_pixels(grid, sizes)
    
    # Apply positions to classes
    for name, pos in positions.items():
        if name in class_lookup:
            class_lookup[name]["position"] = pos
    
    # Compute edge directions
    _compute_directions(relationships, positions, sizes)
    
    return system_spec
