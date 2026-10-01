"""Dark Factory conformance harness.

One architecture, two instantiations: the runner, the Docker driver, the report
format and the HTTP helpers are shared; each track's ``test/`` holds only its own
domain assertions.
"""
