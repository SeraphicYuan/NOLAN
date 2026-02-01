# NOLAN Quality Protocol Module
"""
Quality validation and auto-fix for rendered video content.

Usage:
    from nolan.quality import QualityProtocol

    qa = QualityProtocol()
    result = qa.validate(video_path, expected_text="WE ARE TIRED")

    if not result.passed:
        if result.auto_fixable:
            fixed_path = qa.fix(video_path, result)
"""

from .protocol import QualityProtocol
from .types import QAResult, QAIssue, IssueType, IssueSeverity, QAConfig

__all__ = [
    'QualityProtocol',
    'QAConfig',
    'QAResult',
    'QAIssue',
    'IssueType',
    'IssueSeverity',
]
