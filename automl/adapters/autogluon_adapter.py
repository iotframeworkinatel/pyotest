"""
AutoGluon Adapter — REST client for the AutoGluon Docker container.
Container: autogluon-server (172.20.0.25:8082)
"""
from automl.adapters.rest_base import RESTAutoMLAdapter
from automl.registry import register


@register
class AutoGluonAdapter(RESTAutoMLAdapter):
    FRAMEWORK_NAME = "autogluon"
    BASE_URL = "http://172.20.0.25:8082"
