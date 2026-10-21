import os

from .indic_core import IndicCore
from .indic_flex import IndicFlex
from .mock import Mock
from .whisper import Whisper


def registry() -> dict:
    """Engines shown in the UI. Mock replaces the real ones when TRANSCRIBER_ENGINE=mock."""
    if os.environ.get("TRANSCRIBER_ENGINE") == "mock":
        return {"mock": Mock()}
    return {e.id: e for e in (IndicFlex(), IndicCore(), Whisper())}
