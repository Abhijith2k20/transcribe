from .indic_flex import CORE_LANGS, IndicEngine


class IndicCore(IndicEngine):
    id = "indic-core"
    label = "Indic-Transcribe Core"
    description = "Most accurate for one Indian language at a time."
    languages = [""] + CORE_LANGS
    modes = ["native"]
    gated_repo = "bodhan-ai/indic-transcribe-core"
    pass_mode = False
