"""
Backward compatibility shim for root-level utils.py

DEPRECATED: This module provides backward compatibility for code
importing from root utils.py. New code should use:
    from protomarketmaker.utils import ...

This shim will be removed in version 1.0.0
"""
import warnings

warnings.warn(
    "Importing from root utils.py is deprecated. "
    "Use 'from protomarketmaker.utils import ...' instead",
    DeprecationWarning,
    stacklevel=2
)

# Import everything from legacy_utils for compatibility
from legacy_utils import *  # noqa: F401, F403
