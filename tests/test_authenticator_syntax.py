from custom_components.play24.authenticator import Play24Authenticator
from custom_components.play24.config_flow import Play24ConfigFlow


def test_syntax():
    auth = Play24Authenticator()
    flow = Play24ConfigFlow()
    assert auth is not None
    assert flow is not None
