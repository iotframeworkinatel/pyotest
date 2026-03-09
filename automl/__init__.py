"""
AutoML Package — multi-framework support for IoT vulnerability prediction.

Supported frameworks:
  - H2O AutoML (default, local Java server)
  - AutoGluon (Docker container REST API)
  - PyCaret (Docker container REST API)
  - TPOT (Docker container REST API)
  - auto-sklearn (Docker container REST API)
"""
from automl.base import AutoMLAdapter, AutoMLResult  # noqa: F401
from automl.registry import (                         # noqa: F401
    get_adapter,
    list_all,
    list_available,
    get_framework_status,
    register,
)
