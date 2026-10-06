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
        escaped = summary.replace("\\", "\\\\").replace('"', '\\"')
        jql = (
            f'project = "{self.project_key}" '
            f'AND summary = "{escaped}" '
            "ORDER BY created DESC"
        )

        result = self._request(
            "GET",
            f"/rest/api/3/search/jql?jql={quote(jql)}"
            "&fields=summary,status,issuetype,description,comment",
        )

        return result.get("issues", [])

    def get_issue(self, issue_key):
        return self._request(
            "GET",
            f"/rest/api/3/issue/{quote(issue_key)}"
            "?fields=summary,status,issuetype,description,comment",
        )

    def create_task(self, summary, description, labels=None):
        fields = {
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

        if labels:
            fields["labels"] = labels

        return self._request(
            "POST",
            "/rest/api/3/issue",
            {"fields": fields},
        )

    def update_description(self, issue_key, description):
        payload = {
            "fields": {
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
                }
            }
        }

        return self._request(
            "PUT",
            f"/rest/api/3/issue/{quote(issue_key)}",
            payload,
        )

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

    def search_factory_plan(self, plan_id):
        jql = (
            f'project = "{self.project_key}" '
            'AND labels = "dark-factory-plan" '
            "ORDER BY created ASC"
        )

        result = self._request(
            "GET",
            f"/rest/api/3/search/jql?jql={quote(jql)}"
            "&fields=summary,status,issuetype,description,comment",
        )

        marker = f"DARK_FACTORY_PLAN_ID: {plan_id}"

        return [
            issue
            for issue in result.get("issues", [])
            if marker in self._description_text(issue)
        ]

    @staticmethod
    def _description_text(issue):
        description = (issue.get("fields") or {}).get("description") or {}
        paragraphs = []

        for block in description.get("content", []):
            for item in block.get("content", []):
                value = item.get("text")
                if value:
                    paragraphs.append(value)

        return "\n".join(paragraphs)

    def get_transitions(self, issue_key):
        return self._request(
            "GET",
            f"/rest/api/3/issue/{quote(issue_key)}/transitions",
        ).get("transitions", [])

    def transition_issue(self, issue_key, transition_name):
        transitions = self.get_transitions(issue_key)

        target = next(
            (
                transition
                for transition in transitions
                if str(transition.get("name", "")).strip().lower()
                == transition_name.strip().lower()
            ),
            None,
        )

        if target is None:
            available = ", ".join(
                str(item.get("name", ""))
                for item in transitions
            )
            raise RuntimeError(
                f"No existe transición '{transition_name}' para "
                f"{issue_key}. Disponibles: {available}"
            )

        return self._request(
            "POST",
            f"/rest/api/3/issue/{quote(issue_key)}/transitions",
            {"transition": {"id": target["id"]}},
        )

    def transition_to_finalizada(self, issue_key):
        return self.transition_issue(issue_key, "Finalizada")
