"""
engine/assets - Watermark-Free Archival, Investigative Cards & GPU AI Visual Providers
"""
from engine.assets.ai_gpu_visuals import FluxStillGenerator, LtxVideoGenerator
from engine.assets.ai_visuals import CinematicMotionVisualProvider
from engine.assets.archive_org import InternetArchiveProvider
from engine.assets.manager import VisualAssetManager
from engine.assets.motion import animate_image_to_video
from engine.assets.news_card import InvestigativeCardGenerator
from engine.assets.openverse import OpenverseProvider
from engine.assets.pib import PIBIndiaProvider
from engine.assets.qc_visual import SemanticClipChecker, validate_visual_dimensions

__all__ = [
    "VisualAssetManager",
    "CinematicMotionVisualProvider",
    "PIBIndiaProvider",
    "InternetArchiveProvider",
    "OpenverseProvider",
    "InvestigativeCardGenerator",
    "SemanticClipChecker",
    "FluxStillGenerator",
    "LtxVideoGenerator",
    "validate_visual_dimensions",
    "animate_image_to_video",
]
