"""Peitho — a read-only natural-language reporting + intelligence layer over a gated retail ERP backend.

The useful behaviour is a read-out of the structure of the data (data geometry, not AI): there is no LLM
and no learned model in the significance or decision path. The backend, the store network, the product
taxonomy and the branding all plug in via a cassette (see ``peitho.cassette``); the core carries no
company knowledge. See ``ARCHITECTURE.md`` and ``DESIGN.md``.
"""

__version__ = "0.0.1"
