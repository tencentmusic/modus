"""Public package identity for Modus.

Modus keeps disposable initialization evidence separate from authored narrative
knowledge. The package root intentionally exposes only release metadata: new
capabilities belong to their owning modules instead of accumulating in a
convenience namespace with an accidental compatibility burden.
"""

from typing import Final

__version__: Final = "0.0.6"

__all__ = ["__version__"]
