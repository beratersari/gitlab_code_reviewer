"""
GitLab API client wrapper with comprehensive logging.
"""

import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from logger import get_logger, log_flow_step
from config import get_config

logger = get_logger(__name__)


@dataclass
class MergeRequestInfo:
    """Merge request information."""
    id: int
    iid: int
    title: str
    description: str
    source_branch: str
    target_branch: str
    source_repo_url: str
    author: str
    state: str
    web_url: str


@dataclass
class FileChange:
    """File change in a merge request."""
    old_path: str
    new_path: str
    change_type: str  # added, modified, deleted
    diff: str
    additions: int
    deletions: int


class GitLabClient:
    """GitLab API client for MR operations."""
    
    def __init__(self, gitlab_url: Optional[str] = None, token: Optional[str] = None):
        self.config = get_config()
        self.gitlab_url = gitlab_url or self.config.gitlab_url
        self.token = token or self.config.gitlab_token
        self.session = requests.Session()
        
        if self.token:
            self.session.headers["PRIVATE-TOKEN"] = self.token
        
        log_flow_step(logger, "gitlab_client_init", {
            'gitlab_url': self.gitlab_url,
            'has_token': bool(self.token)
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to GitLab API."""
        url = f"{self.gitlab_url}/api/v4{endpoint}"
        
        logger.debug(f"GitLab API request", extra={
            'method': method,
            'endpoint': endpoint,
            'url': url
        })
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            logger.debug(f"GitLab API response", extra={
                'status_code': response.status_code,
                'endpoint': endpoint
            })
            
            return response.json() if response.content else {}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"GitLab API request failed", extra={
                'method': method,
                'endpoint': endpoint,
                'error': str(e),
                'status_code': getattr(e.response, 'status_code', None)
            })
            raise
    
    def get_merge_request(self, project_id: int, mr_iid: int) -> MergeRequestInfo:
        """Fetch merge request details."""
        log_flow_step(logger, "fetch_mr_start", {
            'project_id': project_id,
            'mr_iid': mr_iid
        })
        
        data = self._make_request("GET", f"/projects/{project_id}/merge_requests/{mr_iid}")
        
        mr_info = MergeRequestInfo(
            id=data["id"],
            iid=data["iid"],
            title=data["title"],
            description=data.get("description", ""),
            source_branch=data["source_branch"],
            target_branch=data["target_branch"],
            source_repo_url=data["source"]["git_http_url"],
            author=data["author"]["username"],
            state=data["state"],
            web_url=data["web_url"]
        )
        
        log_flow_step(logger, "fetch_mr_complete", {
            'mr_id': mr_info.id,
            'title': mr_info.title[:50],
            'author': mr_info.author,
            'source_branch': mr_info.source_branch
        })
        
        return mr_info
    
    def get_merge_request_changes(self, project_id: int, mr_iid: int) -> List[FileChange]:
        """Fetch file changes in a merge request."""
        log_flow_step(logger, "fetch_mr_changes_start", {
            'project_id': project_id,
            'mr_iid': mr_iid
        })
        
        data = self._make_request(
            "GET", 
            f"/projects/{project_id}/merge_requests/{mr_iid}/changes"
        )
        
        changes = []
        for change_data in data.get("changes", []):
            change = FileChange(
                old_path=change_data.get("old_path", ""),
                new_path=change_data.get("new_path", ""),
                change_type=change_data.get("change_type", "modified"),
                diff=change_data.get("diff", ""),
                additions=change_data.get("additions", 0),
                deletions=change_data.get("deletions", 0)
            )
            changes.append(change)
        
        log_flow_step(logger, "fetch_mr_changes_complete", {
            'total_changes': len(changes),
            'additions': sum(c.additions for c in changes),
            'deletions': sum(c.deletions for c in changes)
        })
        
        return changes
    
    def post_merge_request_note(self, project_id: int, mr_iid: int, body: str) -> Dict[str, Any]:
        """Post a note/comment on a merge request."""
        log_flow_step(logger, "post_mr_note_start", {
            'project_id': project_id,
            'mr_iid': mr_iid,
            'body_length': len(body)
        })
        
        result = self._make_request(
            "POST",
            f"/projects/{project_id}/merge_requests/{mr_iid}/notes",
            json={"body": body}
        )
        
        log_flow_step(logger, "post_mr_note_complete", {
            'note_id': result.get('id'),
            'web_url': result.get('web_url')
        })
        
        return result
    
    def post_commit_comment(self, project_id: int, commit_sha: str, path: str, 
                           line: int, note: str) -> Dict[str, Any]:
        """Post a comment on a specific line in a commit."""
        log_flow_step(logger, "post_commit_comment_start", {
            'project_id': project_id,
            'commit_sha': commit_sha[:8],
            'path': path,
            'line': line
        })
        
        result = self._make_request(
            "POST",
            f"/projects/{project_id}/repository/commits/{commit_sha}/comments",
            json={
                "note": note,
                "path": path,
                "line": line,
                "line_type": "new"
            }
        )
        
        log_flow_step(logger, "post_commit_comment_complete", {
            'comment_id': result.get('id')
        })
        
        return result
    
    def get_file_content(self, project_id: int, file_path: str, ref: str) -> Optional[str]:
        """Fetch file content from repository."""
        log_flow_step(logger, "fetch_file_content", {
            'project_id': project_id,
            'file_path': file_path,
            'ref': ref
        })
        
        try:
            # URL encode the file path
            encoded_path = requests.utils.quote(file_path, safe="")
            data = self._make_request(
                "GET",
                f"/projects/{project_id}/repository/files/{encoded_path}/raw",
                params={"ref": ref}
            )
            return data if isinstance(data, str) else None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"File not found", extra={
                    'file_path': file_path,
                    'ref': ref
                })
                return None
            raise


class MockGitLabClient(GitLabClient):
    """Mock GitLab client for testing without real GitLab access."""
    
    def __init__(self, mock_repo_path: Optional[Path] = None):
        # Don't call super().__init__() to avoid needing real credentials
        self.config = get_config()
        self.mock_repo_path = mock_repo_path or Path(__file__).parent.parent / "sample_project"
        logger.info(f"Using MockGitLabClient with repo: {self.mock_repo_path}")
    
    def get_merge_request(self, project_id: int, mr_iid: int) -> MergeRequestInfo:
        """Return mock MR info."""
        log_flow_step(logger, "mock_fetch_mr", {
            'project_id': project_id,
            'mr_iid': mr_iid
        })
        
        return MergeRequestInfo(
            id=1,
            iid=mr_iid,
            title="Sample Merge Request for Testing",
            description="This is a mock MR for testing the reviewer.",
            source_branch="feature/test-branch",
            target_branch="main",
            source_repo_url=str(self.mock_repo_path),
            author="testuser",
            state="opened",
            web_url="http://mock-gitlab/test/project/-/merge_requests/1"
        )
    
    def get_merge_request_changes(self, project_id: int, mr_iid: int) -> List[FileChange]:
        """Return mock changes from sample files."""
        log_flow_step(logger, "mock_fetch_changes", {
            'project_id': project_id,
            'mr_iid': mr_iid
        })
        
        # Create a sample Python file with some issues to review
        sample_diff = '''
diff --git a/src/example.py b/src/example.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/example.py
@@ -0,0 +1,45 @@
+import os
+import sys
+
+def process_data(data):
+    result = []
+    for i in range(len(data)):
+        for j in range(len(data)):
+            if data[i] == data[j]:
+                result.append(data[i])
+    return result
+
+def get_user_input():
+    user_id = input("Enter user ID: ")
+    query = f"SELECT * FROM users WHERE id = {user_id}"
+    return query
+
+class userData:
+    def __init__(self, name, age):
+        self.name = name
+        self.age = age
+    
+    def print_info(self):
+        print("Name: " + self.name + ", Age: " + str(self.age))
+
+def calculate(x, y):
+    try:
+        result = x / y
+    except:
+        result = 0
+    return result
+
+API_KEY = "sk-1234567890abcdef"
+
+def main():
+    data = [1, 2, 3, 4, 5]
+    processed = process_data(data)
+    print(processed)
+    
+    query = get_user_input()
+    print(query)
+    
+    user = userData("John", 30)
+    user.print_info()
+    
+    result = calculate(10, 0)
+    print(result)
+
+if __name__ == "__main__":
+    main()
'''
        
        return [
            FileChange(
                old_path="",
                new_path="src/example.py",
                change_type="added",
                diff=sample_diff,
                additions=45,
                deletions=0
            )
        ]
    
    def post_merge_request_note(self, project_id: int, mr_iid: int, body: str) -> Dict[str, Any]:
        """Log the note instead of posting."""
        log_flow_step(logger, "mock_post_note", {
            'project_id': project_id,
            'mr_iid': mr_iid,
            'body_preview': body[:200] + "..." if len(body) > 200 else body
        })
        
        # Write review to file for inspection
        review_file = self.config.temp_dir / f"mock_review_{mr_iid}.md"
        with open(review_file, 'w') as f:
            f.write(body)
        
        logger.info(f"Mock review saved to: {review_file}")
        
        return {"id": 999, "web_url": "http://mock-gitlab/test/note/999"}
    
    def post_commit_comment(self, project_id: int, commit_sha: str, path: str,
                           line: int, note: str) -> Dict[str, Any]:
        """Log the comment instead of posting."""
        log_flow_step(logger, "mock_post_comment", {
            'path': path,
            'line': line,
            'note_preview': note[:100]
        })
        return {"id": 999}
    
    def get_file_content(self, project_id: int, file_path: str, ref: str) -> Optional[str]:
        """Read file from mock repository."""
        full_path = self.mock_repo_path / file_path
        if full_path.exists():
            with open(full_path, 'r') as f:
                return f.read()
        return None
