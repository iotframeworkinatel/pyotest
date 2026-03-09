"""
auto-sklearn Adapter — REST client for the auto-sklearn Docker container.
Container: autosklearn-server (172.20.0.28:8085)
"""
from automl.adapters.rest_base import RESTAutoMLAdapter
from automl.registry import register


@register
class AutoSklearnAdapter(RESTAutoMLAdapter):
    FRAMEWORK_NAME = "autosklearn"
    BASE_URL = "http://172.20.0.28:8085"
