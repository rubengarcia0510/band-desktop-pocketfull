import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class JiraClient:
    def __init__(self):
        self.base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
        self.email = os.environ["JIRA_EMAIL"]
        self.api_token = os.environ["JIRA_API_TOKEN"]
        self.project_key = os.environ.get("JIRA_PROJECT_KEY", "PDF")

    def _request(self, method, path, payload=None):
        url = f"{self.base_url}{path}"
        credentials = base64.b64encode(
            f"{self.email}:{self.api_token}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"Jira API error {exc.code} {method} {path}: {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Jira connection error {method} {path}: {exc.reason}"
            ) from exc

    def search_by_summary(self, summary):
        jql = (
            f'project = "{self.project_key}" '
            f'AND summary ~ "\\"{summary}\\"" '
            "ORDER BY created DESC"
        )

        result = self._request(
            "GET",
            f"/rest/api/3/search/jql?jql={quote(jql)}"
            "&fields=summary,status,issuetype",
        )

        return result.get("issues", [])

    def create_task(self, summary, description):
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description,
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {"name": "Tarea"},
            }
        }

        return self._request("POST", "/rest/api/3/issue", payload)

    def add_comment(self, issue_key, comment):
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": comment,
                            }
                        ],
                    }
                ],
            }
        }

        return self._request(
            "POST",
            f"/rest/api/3/issue/{quote(issue_key)}/comment",
            payload,
        )
