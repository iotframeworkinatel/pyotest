"""
TPOT Adapter — REST client for the TPOT Docker container.
Container: tpot-server (172.20.0.27:8084)
"""
from automl.adapters.rest_base import RESTAutoMLAdapter
from automl.registry import register


@register
class TPOTAdapter(RESTAutoMLAdapter):
    FRAMEWORK_NAME = "tpot"
    BASE_URL = "http://172.20.0.27:8084"
