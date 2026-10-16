from __future__ import annotations

from srw.runtime.capabilities import CapabilityRegistry


def register_default_lazy_capabilities(registry: CapabilityRegistry) -> None:
    """Register optional capability factories without importing their heavy dependencies."""
    if not registry.available("provider.deepseek"):
        registry.register("provider.deepseek", _openai_compatible_provider)
    if not registry.available("provider.openai_compatible"):
        registry.register("provider.openai_compatible", _openai_compatible_provider)
    if not registry.available("document_importer"):
        registry.register("document_importer", _rich_document_importer)


def _openai_compatible_provider():
    from srw.providers.openai_compatible import build_openai_compatible_provider

    return build_openai_compatible_provider()


def _rich_document_importer():
    from srw.intake.rich_document import build_rich_document_importer

    return build_rich_document_importer()
