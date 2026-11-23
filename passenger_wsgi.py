"""Source entry point; hosted bootstraps may delegate without being replaced.

The module alias preserves imports and monkeypatches of the historical
passenger_wsgi module while production code lives in the deployable package.
"""
import sys
from conest_app import wsgi_runtime as _runtime

application = _runtime.application
sys.modules[__name__] = _runtime
