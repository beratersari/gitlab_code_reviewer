#!/usr/bin/env python3
"""
Mock GitLab Server for Testing Webhooks

This script simulates GitLab webhook events without needing actual GitLab access.
It can send test webhooks to your local reviewer server.
"""

import argparse
import json
import requests
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logger import setup_logging, get_logger

setup_logging()
logger = get_logger("mock_gitlab")


class MockGitLabWebhook:
    """Simulates GitLab webhook events."""
    
    def __init__(self, reviewer_url: str = "http://localhost:8000", 
                 webhook_secret: str = None):
        self.reviewer_url = reviewer_url.rstrip("/")
        self.webhook_secret = webhook_secret
        logger.info(f"Mock GitLab initialized. Target: {reviewer_url}")
    
    def _send_webhook(self, event_type: str, payload: dict) -> dict:
        """Send webhook payload to reviewer."""
        url = f"{self.reviewer_url}/webhook"
        
        headers = {
            "Content-Type": "application/json",
            "X-Gitlab-Event": event_type,
            "X-Gitlab-Token": self.webhook_secret or ""
        }
        
        logger.info(f"Sending {event_type} webhook to {url}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            logger.info(f"Webhook accepted: {response.status_code}")
            logger.debug(f"Response: {response.json()}")
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Webhook failed: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
    
    def trigger_mr_open(self, project_id: int = 123, mr_iid: int = 1,
                       source_branch: str = "feature/test") -> dict:
        """Simulate MR open event."""
        
        payload = {
            "object_kind": "merge_request",
            "event_type": "merge_request",
            "project": {
                "id": project_id,
                "name": "Test Project",
                "web_url": "https://gitlab.com/test/project"
            },
            "object_attributes": {
                "id": 1,
                "iid": mr_iid,
                "target_project_id": project_id,
                "source_project_id": project_id,
                "title": "Add new feature",
                "description": "This MR adds a new feature",
                "state": "opened",
                "action": "open",
                "source_branch": source_branch,
                "target_branch": "main",
                "source": {
                    "git_http_url": "https://gitlab.com/test/project.git"
                },
                "author_id": 1
            },
            "author": {
                "id": 1,
                "name": "Test User",
                "username": "testuser"
            }
        }
        
        return self._send_webhook("Merge Request Hook", payload)
    
    def trigger_mr_update(self, project_id: int = 123, mr_iid: int = 1) -> dict:
        """Simulate MR update event (new commits pushed)."""
        
        payload = {
            "object_kind": "merge_request",
            "event_type": "merge_request",
            "project": {
                "id": project_id,
                "name": "Test Project",
                "web_url": "https://gitlab.com/test/project"
            },
            "object_attributes": {
                "id": 1,
                "iid": mr_iid,
                "target_project_id": project_id,
                "title": "Add new feature",
                "description": "Updated with new changes",
                "state": "opened",
                "action": "update",
                "source_branch": "feature/test",
                "target_branch": "main",
                "source": {
                    "git_http_url": "https://gitlab.com/test/project.git"
                }
            }
        }
        
        return self._send_webhook("Merge Request Hook", payload)
    
    def trigger_mr_comment(self, project_id: int = 123, mr_iid: int = 1,
                          comment: str = "/review") -> dict:
        """Simulate MR comment with /review command."""
        
        payload = {
            "object_kind": "note",
            "event_type": "note",
            "project": {
                "id": project_id,
                "name": "Test Project"
            },
            "object_attributes": {
                "id": 1,
                "noteable_type": "MergeRequest",
                "noteable_id": 1,
                "note": comment,
                "author_id": 1
            },
            "merge_request": {
                "id": 1,
                "iid": mr_iid,
                "target_project_id": project_id,
                "source_branch": "feature/test",
                "target_branch": "main"
            },
            "author": {
                "id": 1,
                "name": "Test User",
                "username": "testuser"
            }
        }
        
        return self._send_webhook("Note Hook", payload)
    
    def test_connection(self) -> bool:
        """Test connection to reviewer server."""
        try:
            response = requests.get(f"{self.reviewer_url}/health")
            response.raise_for_status()
            data = response.json()
            logger.info(f"Reviewer server is healthy: {data}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Cannot connect to reviewer server: {e}")
            return False


def interactive_mode():
    """Run interactive testing mode."""
    print("\n" + "=" * 60)
    print("GitLab Mock Webhook Server - Interactive Mode")
    print("=" * 60 + "\n")
    
    # Get configuration
    reviewer_url = input("Reviewer URL [http://localhost:8000]: ").strip()
    if not reviewer_url:
        reviewer_url = "http://localhost:8000"
    
    secret = input("Webhook secret (optional): ").strip()
    if not secret:
        secret = None
    
    mock = MockGitLabWebhook(reviewer_url, secret)
    
    # Test connection
    print("\nTesting connection to reviewer...")
    if not mock.test_connection():
        print("❌ Failed to connect. Is the reviewer server running?")
        return
    print("✅ Connected successfully!\n")
    
    while True:
        print("\nOptions:")
        print("1. Trigger MR Open event")
        print("2. Trigger MR Update event")
        print("3. Trigger MR Comment (/review)")
        print("4. Trigger custom comment")
        print("5. Test connection")
        print("6. Exit")
        
        choice = input("\nSelect option [1-6]: ").strip()
        
        try:
            if choice == "1":
                project_id = input("Project ID [123]: ").strip() or "123"
                mr_iid = input("MR IID [1]: ").strip() or "1"
                result = mock.trigger_mr_open(int(project_id), int(mr_iid))
                print(f"✅ Result: {result}")
                
            elif choice == "2":
                project_id = input("Project ID [123]: ").strip() or "123"
                mr_iid = input("MR IID [1]: ").strip() or "1"
                result = mock.trigger_mr_update(int(project_id), int(mr_iid))
                print(f"✅ Result: {result}")
                
            elif choice == "3":
                project_id = input("Project ID [123]: ").strip() or "123"
                mr_iid = input("MR IID [1]: ").strip() or "1"
                result = mock.trigger_mr_comment(int(project_id), int(mr_iid))
                print(f"✅ Result: {result}")
                
            elif choice == "4":
                project_id = input("Project ID [123]: ").strip() or "123"
                mr_iid = input("MR IID [1]: ").strip() or "1"
                comment = input("Comment text [/review]: ").strip() or "/review"
                result = mock.trigger_mr_comment(int(project_id), int(mr_iid), comment)
                print(f"✅ Result: {result}")
                
            elif choice == "5":
                if mock.test_connection():
                    print("✅ Connection OK")
                else:
                    print("❌ Connection failed")
                    
            elif choice == "6":
                print("Goodbye!")
                break
                
            else:
                print("Invalid option. Please try again.")
                
        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Mock GitLab Webhook Server for Testing"
    )
    parser.add_argument(
        "--reviewer-url", "-u",
        default="http://localhost:8000",
        help="URL of the reviewer webhook endpoint"
    )
    parser.add_argument(
        "--secret", "-s",
        default=None,
        help="Webhook secret for authentication"
    )
    parser.add_argument(
        "--event", "-e",
        choices=["mr-open", "mr-update", "mr-comment"],
        help="Event type to trigger (non-interactive mode)"
    )
    parser.add_argument(
        "--project-id", "-p",
        type=int,
        default=123,
        help="Project ID for the event"
    )
    parser.add_argument(
        "--mr-iid", "-m",
        type=int,
        default=1,
        help="MR IID for the event"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode"
    )
    
    args = parser.parse_args()
    
    if args.interactive or len(sys.argv) == 1:
        interactive_mode()
        return
    
    # Non-interactive mode
    mock = MockGitLabWebhook(args.reviewer_url, args.secret)
    
    # Test connection first
    if not mock.test_connection():
        sys.exit(1)
    
    # Trigger event
    if args.event == "mr-open":
        result = mock.trigger_mr_open(args.project_id, args.mr_iid)
    elif args.event == "mr-update":
        result = mock.trigger_mr_update(args.project_id, args.mr_iid)
    elif args.event == "mr-comment":
        result = mock.trigger_mr_comment(args.project_id, args.mr_iid)
    else:
        parser.print_help()
        sys.exit(1)
    
    print(f"\nResult: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
