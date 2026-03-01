# Utils package — lazy imports only to avoid pulling heavy dependencies
# (history, reports, vulnerability_tester) in lightweight contexts like
# the dashboard API container.
#
# Import specific submodules directly:
#   from utils.protocols import PORT_PROTOCOL_MAP
#   from utils.tester import general_tester
#   from utils.default_data import COMMON_CREDENTIALS
