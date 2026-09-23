# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""
Fully automated job application autopilot.

Handles:
- Job matching and selection
- AI-powered resume tailoring
- AI-powered cover letter generation
- Headless browser form filling
- Automatic submission
- Application tracking
"""

from .engine import AutopilotEngine
from .tailor import TailorEngine
from .browser import BrowserAutomator

__all__ = ["AutopilotEngine", "TailorEngine", "BrowserAutomator"]
