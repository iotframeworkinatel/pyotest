"""
PyCaret Adapter — REST client for the PyCaret Docker container.
Container: pycaret-server (172.20.0.26:8083)
"""
from automl.adapters.rest_base import RESTAutoMLAdapter
from automl.registry import register


@register
class PyCaretAdapter(RESTAutoMLAdapter):
    FRAMEWORK_NAME = "pycaret"
    BASE_URL = "http://172.20.0.26:8083"
