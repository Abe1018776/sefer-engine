#!/usr/bin/env python3
"""
engine/overrides.py — Manual Override System

Reads overrides.json and provides constraints to the solver.
Supports per-page overrides (force breaks, extra leading, keep-with-next)
and global settings (min lines, imbalance ratios).
"""

import json
from pathlib import Path

DEFAULT_GLOBAL = {
    "min_body_lines": 2,
    "min_column_lines": 2,
    "max_column_imbalance_ratio": 0.3,
}


class OverrideManager:
    """Manage manual overrides for the page solver."""

    def __init__(self, overrides_path: str = None):
        """Load overrides from JSON file.
        
        Args:
            overrides_path: Path to overrides.json. If None or missing, uses defaults.
        """
        self.page_overrides = {}
        self.global_settings = dict(DEFAULT_GLOBAL)
        
        if overrides_path:
            path = Path(overrides_path)
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.page_overrides = data.get('page_overrides', {})
                    if 'global' in data:
                        self.global_settings.update(data['global'])
                    print(f"  Loaded overrides: {len(self.page_overrides)} page overrides")
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"  Warning: Could not load overrides: {e}")

    def get_page_override(self, page_num: int) -> dict:
        """Get override settings for a specific page number.
        
        Returns dict with possible keys:
            - force_break_before: bool
            - extra_leading_pt: float
            - keep_with_next: list of entry IDs
            - max_body_lines: int
            - max_column_lines: int
        """
        return self.page_overrides.get(str(page_num), {})

    def should_force_break(self, page_num: int) -> bool:
        """Check if a page break should be forced before this page."""
        override = self.get_page_override(page_num)
        return override.get('force_break_before', False)

    def get_extra_leading(self, page_num: int) -> float:
        """Get extra leading (spacing) adjustment for this page in pt."""
        override = self.get_page_override(page_num)
        return override.get('extra_leading_pt', 0.0)

    def get_keep_with_next(self, page_num: int) -> list:
        """Get list of entry IDs that should be kept with next content."""
        override = self.get_page_override(page_num)
        return override.get('keep_with_next', [])

    @property
    def min_body_lines(self) -> int:
        return self.global_settings['min_body_lines']

    @property
    def min_column_lines(self) -> int:
        return self.global_settings['min_column_lines']

    @property
    def max_imbalance_ratio(self) -> float:
        return self.global_settings['max_column_imbalance_ratio']
