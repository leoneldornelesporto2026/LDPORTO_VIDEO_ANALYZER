"""Explicit, presentation-layer analysis presets. No hardware or AI invocation.

These are named configuration choices, not measured quality/performance claims.
Only ASR model and existing Ollama profile are set by the UI.
"""
PROFILE_CHOICES = (
    "Personalizado",
    "Qualidade (large-v3)",
    "Equilibrado (medium)",
    "Rápido (turbo)",
)
_PRESETS = {
    "Qualidade (large-v3)": {"asr_model": "large-v3", "ollama_profile": "max"},
    "Equilibrado (medium)": {"asr_model": "medium", "ollama_profile": "balanced"},
    "Rápido (turbo)": {"asr_model": "turbo", "ollama_profile": "fast"},
}


def preset_settings(profile):
    """Return a fresh mapping, or None for custom selections (no changes)."""
    if profile == "Personalizado":
        return None
    if profile not in _PRESETS:
        raise ValueError("Perfil nao reconhecido: " + str(profile))
    return dict(_PRESETS[profile])


def describe_effective_profile(profile, model, device, ollama_enabled, ollama_model, ollama_profile):
    """Explain actual options; never imply model availability or completed checks."""
    semantic = (
        "Ollama " + str(ollama_model) + " / " + str(ollama_profile)
        if ollama_enabled else "heurística (Ollama desligado)"
    )
    return (
        "Selecionado: " + str(profile) +
        "  |  ASR: " + str(model) +
        "  |  Dispositivo: " + str(device) +
        "  |  Semântica: " + semantic +
        "  |  Desempenho e qualidade não medidos."
    )
