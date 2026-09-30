# The conformance harness itself, with a browser, so the suites can run from
# inside the internal network the service under test is attached to. That network
# has no route off the machine, which is how "no outbound at run time" is enforced.
FROM python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
 && playwright install --with-deps chromium

WORKDIR /work
