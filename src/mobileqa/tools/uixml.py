"""
UI XML parsing and interaction utilities for Android UI hierarchy.
"""
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

from .adb import ADB


@dataclass
class UINode:
    """Represents a UI element from the XML hierarchy."""
    tag: str
    index: int
    text: str
    resource_id: str
    class_name: str
    package: str
    content_desc: str
    checkable: bool
    checked: bool
    clickable: bool
    enabled: bool
    focusable: bool
    focused: bool
    scrollable: bool
    long_clickable: bool
    password: bool
    selected: bool
    bounds: Tuple[int, int, int, int]  # (left, top, right, bottom)

    @property
    def center(self) -> Tuple[int, int]:
        """Get center coordinates of the element."""
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    @property
    def width(self) -> int:
        """Get width of the element."""
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        """Get height of the element."""
        return self.bounds[3] - self.bounds[1]


class UIXMLParser:
    """Parser for Android UI XML hierarchy."""

    def __init__(self, adb: ADB):
        """
        Initialize UI XML parser.

        Args:
            adb: ADB instance for device communication
        """
        self.adb = adb

    def dump_ui(self, output_path: Optional[str] = None) -> str:
        """
        Dump UI hierarchy to XML.

        Args:
            output_path: Optional local path to save XML.
                        If None, uses temporary file.

        Returns:
            Path to the XML file
        """
        # Dump UI hierarchy on device
        device_xml_path = '/sdcard/window_dump.xml'
        self.adb._run_command(['shell', 'uiautomator', 'dump', device_xml_path])

        # Determine output path
        if output_path is None:
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False)
            output_path = temp_file.name
            temp_file.close()
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Pull XML file from device
        self.adb._run_command(['pull', device_xml_path, output_path])

        return output_path

    def parse_bounds(self, bounds_str: str) -> Tuple[int, int, int, int]:
        """
        Parse bounds string to coordinates.

        Args:
            bounds_str: Bounds in format "[left,top][right,bottom]"

        Returns:
            Tuple of (left, top, right, bottom)
        """
        # Extract numbers from "[left,top][right,bottom]" format
        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
        if match:
            return tuple(map(int, match.groups()))
        return (0, 0, 0, 0)

    def parse_xml(self, xml_path: str) -> List[UINode]:
        """
        Parse UI XML file into UINode objects.

        Args:
            xml_path: Path to XML file

        Returns:
            List of UINode objects
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        nodes = []
        self._parse_node(root, nodes)
        return nodes

    def _parse_node(self, element: ET.Element, nodes: List[UINode]):
        """Recursively parse XML element tree."""
        # Parse current node
        bounds_str = element.get('bounds', '[0,0][0,0]')
        bounds = self.parse_bounds(bounds_str)

        node = UINode(
            tag=element.tag,
            index=int(element.get('index', '0')),
            text=element.get('text', ''),
            resource_id=element.get('resource-id', ''),
            class_name=element.get('class', ''),
            package=element.get('package', ''),
            content_desc=element.get('content-desc', ''),
            checkable=element.get('checkable', 'false') == 'true',
            checked=element.get('checked', 'false') == 'true',
            clickable=element.get('clickable', 'false') == 'true',
            enabled=element.get('enabled', 'true') == 'true',
            focusable=element.get('focusable', 'false') == 'true',
            focused=element.get('focused', 'false') == 'true',
            scrollable=element.get('scrollable', 'false') == 'true',
            long_clickable=element.get('long-clickable', 'false') == 'true',
            password=element.get('password', 'false') == 'true',
            selected=element.get('selected', 'false') == 'true',
            bounds=bounds
        )

        nodes.append(node)

        # Parse children
        for child in element:
            self._parse_node(child, nodes)

    def find_by_text(self, nodes: List[UINode], text: str, exact: bool = False) -> List[UINode]:
        """
        Find UI nodes by text content with fallback matching.

        Tries in order:
        1. Exact match (case-sensitive)
        2. Exact match (case-insensitive)
        3. Substring match (case-insensitive)

        Args:
            nodes: List of UINode objects to search
            text: Text to search for
            exact: If True, only try exact matches

        Returns:
            List of matching UINode objects (best matches first)
        """
        exact_matches = []
        case_insensitive_matches = []
        substring_matches = []

        text_lower = text.lower()

        for node in nodes:
            node_text = node.text
            node_desc = node.content_desc

            # Exact match (case-sensitive)
            if node_text == text or node_desc == text:
                exact_matches.append(node)
                continue

            if not exact:
                # Case-insensitive exact match
                if node_text.lower() == text_lower or node_desc.lower() == text_lower:
                    case_insensitive_matches.append(node)
                    continue

                # Substring match
                if text_lower in node_text.lower() or text_lower in node_desc.lower():
                    substring_matches.append(node)

        # Return best matches first
        if exact_matches:
            return exact_matches
        if case_insensitive_matches:
            return case_insensitive_matches
        return substring_matches

    def find_by_resource_id(self, nodes: List[UINode], resource_id: str) -> List[UINode]:
        """
        Find UI nodes by resource ID.

        Args:
            nodes: List of UINode objects to search
            resource_id: Resource ID to search for (can be partial)

        Returns:
            List of matching UINode objects
        """
        return [node for node in nodes if resource_id in node.resource_id]

    def find_clickable(self, nodes: List[UINode]) -> List[UINode]:
        """
        Find all clickable UI nodes.

        Args:
            nodes: List of UINode objects to search

        Returns:
            List of clickable UINode objects
        """
        return [node for node in nodes if node.clickable and node.enabled]

    def tap_by_text(self, text: str, exact: bool = False, wait_after: float = 0.0) -> bool:
        """
        Find element by text and tap its center.

        If multiple matches, prefers:
        1. Clickable elements
        2. Largest clickable bounds
        3. Closest to screen center

        Args:
            text: Text to search for
            exact: If True, match exactly; otherwise substring match
            wait_after: Seconds to wait after tap (default 0.0, ZERO WAIT)

        Returns:
            True if element found and tapped
        """
        # Dump and parse UI
        xml_path = self.dump_ui()
        nodes = self.parse_xml(xml_path)

        # Find matching nodes
        matches = self.find_by_text(nodes, text, exact=exact)

        if not matches:
            return False

        # Choose best match if multiple
        best_match = self._choose_best_match(matches)

        # Tap the best match
        x, y = best_match.center
        self.adb.tap_xy(x, y, wait_after=wait_after)
        return True

    def _choose_best_match(self, matches: List[UINode]) -> UINode:
        """
        Choose the best match from multiple candidates.

        Prefers:
        1. Clickable elements
        2. Largest area (for clickable)
        3. Closest to screen center

        Args:
            matches: List of matching nodes

        Returns:
            Best matching node
        """
        if len(matches) == 1:
            return matches[0]

        # Filter to clickable if any
        clickable = [m for m in matches if m.clickable]
        if clickable:
            # Choose largest clickable element
            return max(clickable, key=lambda n: n.width * n.height)

        # No clickable elements, choose closest to center
        # Assume typical phone screen center around 540x1000
        screen_center_x = 540
        screen_center_y = 1000

        def distance_to_center(node: UINode) -> float:
            cx, cy = node.center
            return ((cx - screen_center_x) ** 2 + (cy - screen_center_y) ** 2) ** 0.5

        return min(matches, key=distance_to_center)

    def get_ui_summary(self, xml_path: str) -> str:
        """
        Get a human-readable summary of UI elements.

        Args:
            xml_path: Path to UI XML file

        Returns:
            Text summary of important UI elements
        """
        nodes = self.parse_xml(xml_path)

        # Filter to interesting elements (have text, content-desc, or are clickable)
        interesting = [
            node for node in nodes
            if node.text or node.content_desc or node.clickable
        ]

        summary_lines = []
        for node in interesting:
            parts = []
            if node.text:
                parts.append(f'text="{node.text}"')
            if node.content_desc:
                parts.append(f'desc="{node.content_desc}"')
            if node.resource_id:
                # Simplify resource ID
                res_id = node.resource_id.split('/')[-1] if '/' in node.resource_id else node.resource_id
                parts.append(f'id={res_id}')

            attrs = []
            if node.clickable:
                attrs.append('clickable')
            if node.scrollable:
                attrs.append('scrollable')
            if node.checked:
                attrs.append('checked')
            if not node.enabled:
                attrs.append('disabled')

            if attrs:
                parts.append(f"[{','.join(attrs)}]")

            parts.append(f"bounds={node.bounds}")

            summary_lines.append(' '.join(parts))

        return '\n'.join(summary_lines)
