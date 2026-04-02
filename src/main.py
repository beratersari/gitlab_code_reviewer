"""
GitLab Opencode Reviewer - Main Application

FastAPI-based webhook server for receiving GitLab events and triggering code reviews.
"""

import os
import sys
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from logger import setup_logging, get_logger, log_flow_step
from config import get_config, Config
from gitlab_client import GitLabClient, MockGitLabClient, FileChange
from opencode_wrapper import OpencodeReviewer, RepositoryCloner

# Setup logging
main_logger = setup_logging()
logger = get_logger(__name__)

# Track application state
app_state = {
    'reviews_in_progress': 0,
    'reviews_completed': 0,
    'reviews_failed': 0
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    config = get_config()
    logger.info("=" * 60)
    logger.info("GitLab Opencode Reviewer Starting")
    logger.info("=" * 60)
    logger.info(f"Configuration: {config.to_dict()}")
    
    # Validate configuration
    issues = config.validate()
    if issues:
        logger.warning("Configuration issues detected:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("Configuration validated successfully")
    
    yield
    
    # Shutdown
    logger.info("=" * 60)
    logger.info("GitLab Opencode Reviewer Shutting Down")
    logger.info(f"Final stats: {app_state}")
    logger.info("=" * 60)


app = FastAPI(
    title="GitLab Opencode Reviewer",
    description="Automated code review using opencode AI",
    version="1.0.0",
    lifespan=lifespan
)


def verify_webhook_secret(request: Request) -> bool:
    """Verify webhook secret if configured."""
    config = get_config()
    if not config.webhook_secret:
        return True
    
    secret = request.headers.get("X-Gitlab-Token")
    return secret == config.webhook_secret


def is_code_file(file_path: str) -> bool:
    """Check if file should be reviewed based on extension."""
    config = get_config()
    ext = Path(file_path).suffix.lower()
    return ext in config.review_extensions


def format_review_comment(results: list) -> str:
    """Format review results as a GitLab markdown comment."""
    lines = [
        "## 🤖 Automated Code Review",
        "",
        f"Reviewed with model: `{get_config().opencode_model}`",
        "",
        "---",
        ""
    ]
    
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count
    
    lines.append(f"**Summary**: {success_count} files reviewed successfully")
    if fail_count > 0:
        lines.append(f"⚠️ {fail_count} files failed to review")
    lines.append("")
    
    for result in results:
        lines.append(f"### `{result.file_path}`")
        lines.append("")
        
        if result.success:
            lines.append(result.review_text)
        else:
            lines.append(f"❌ **Review Failed**: {result.error_message}")
        
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


async def process_merge_request(project_id: int, mr_iid: int, 
                                use_mock: bool = False):
    """
    Process a merge request review.
    
    This is the main workflow:
    1. Fetch MR info and changes from GitLab
    2. Clone the repository
    3. Load project review rules
    4. Review each changed file with opencode
    5. Post review comments to MR
    """
    config = get_config()
    app_state['reviews_in_progress'] += 1
    
    log_flow_step(logger, "review_workflow_start", {
        'project_id': project_id,
        'mr_iid': mr_iid,
        'use_mock': use_mock
    })
    
    cloner = RepositoryCloner()
    repo_path: Optional[Path] = None
    
    try:
        # Initialize GitLab client
        # Use mock client if: use_mock parameter is True OR simulation_mode is enabled in config
        if use_mock or config.simulation_mode:
            if config.simulation_mode:
                logger.info("Running in SIMULATION MODE - using local sample_project")
            gl = MockGitLabClient()
        else:
            gl = GitLabClient()
        
        # Step 1: Fetch MR info
        logger.info(f"Step 1: Fetching MR info...")
        mr = gl.get_merge_request(project_id, mr_iid)
        
        # Step 2: Fetch changes
        logger.info(f"Step 2: Fetching MR changes...")
        changes = gl.get_merge_request_changes(project_id, mr_iid)
        
        # Filter to only code files
        code_changes = [c for c in changes if is_code_file(c.new_path)]
        skipped = len(changes) - len(code_changes)
        
        log_flow_step(logger, "changes_filtered", {
            'total_changes': len(changes),
            'code_changes': len(code_changes),
            'skipped': skipped
        })
        
        if not code_changes:
            logger.info("No code files to review")
            app_state['reviews_completed'] += 1
            return
        
        # Step 3: Clone repository (if not using mock or simulation mode)
        if use_mock or config.simulation_mode:
            logger.info(f"Step 3: Using mock repository at: {gl.mock_repo_path}")
            repo_path = gl.mock_repo_path
        else:
            logger.info(f"Step 3: Cloning repository...")
            repo_path = cloner.clone(
                mr.source_repo_url,
                mr.source_branch,
                token=config.gitlab_token
            )
        
        # Step 4: Initialize reviewer
        logger.info(f"Step 4: Initializing opencode reviewer...")
        issue_key = f"MR-{mr_iid}"
        reviewer = OpencodeReviewer(repo_path, issue_key=issue_key)
        
        # Step 5: Review files
        logger.info(f"Step 5: Reviewing {len(code_changes)} files...")
        results = []
        
        for i, change in enumerate(code_changes, 1):
            logger.info(f"Reviewing file {i}/{len(code_changes)}: {change.new_path}")
            
            # Get full file content for context (optional, for smaller files)
            file_content = None
            if change.additions + change.deletions < 100:
                file_content = gl.get_file_content(project_id, change.new_path, mr.source_branch)
            
            result = reviewer.review_file(
                change.new_path,
                change.diff,
                file_content
            )
            results.append(result)
        
        # Step 6: Post review
        logger.info(f"Step 6: Posting review to MR...")
        review_body = format_review_comment(results)
        gl.post_merge_request_note(project_id, mr_iid, review_body)
        
        log_flow_step(logger, "review_workflow_complete", {
            'project_id': project_id,
            'mr_iid': mr_iid,
            'files_reviewed': len(results),
            'success': True
        })
        
        app_state['reviews_completed'] += 1
        
    except Exception as e:
        logger.error(f"Review workflow failed: {e}", exc_info=True)
        app_state['reviews_failed'] += 1
        
        # Try to post error message to MR
        try:
            if not use_mock:
                gl = GitLabClient()
                gl.post_merge_request_note(
                    project_id, 
                    mr_iid,
                    f"❌ **Code Review Failed**\n\nError: {str(e)}"
                )
        except:
            pass
        
        raise
        
    finally:
        app_state['reviews_in_progress'] -= 1
        
        # Cleanup cloned repo (but not in mock/simulation mode)
        if repo_path and not use_mock and not config.simulation_mode:
            cloner.cleanup(repo_path)


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "service": "GitLab Opencode Reviewer",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "reviews_in_progress": app_state['reviews_in_progress'],
        "reviews_completed": app_state['reviews_completed'],
        "reviews_failed": app_state['reviews_failed']
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive GitLab webhooks.
    
    Supports:
    - Merge Request Hook (open, update)
    - Note Hook (for /review commands)
    """
    log_flow_step(logger, "webhook_received", {
        'remote_addr': request.client.host if request.client else 'unknown'
    })
    
    # Verify secret
    if not verify_webhook_secret(request):
        logger.warning("Webhook secret verification failed")
        raise HTTPException(status_code=401, detail="Invalid secret")
    
    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Get event type
    event_type = request.headers.get("X-Gitlab-Event", "unknown")
    object_kind = payload.get("object_kind")
    
    logger.info(f"Webhook received: {event_type} / {object_kind}")
    
    # Handle Merge Request events
    if object_kind == "merge_request":
        action = payload.get("object_attributes", {}).get("action")
        
        if action in ["open", "update", "reopen"]:
            project_id = payload["object_attributes"]["target_project_id"]
            mr_iid = payload["object_attributes"]["iid"]
            
            logger.info(f"Triggering review for MR !{mr_iid} (action: {action})")
            
            # Process in background
            background_tasks.add_task(process_merge_request, project_id, mr_iid)
            
            return JSONResponse({
                "status": "accepted",
                "message": f"Review queued for MR !{mr_iid}"
            })
        else:
            logger.info(f"Ignoring MR action: {action}")
            return JSONResponse({"status": "ignored", "reason": f"action={action}"})
    
    # Handle Note/Comment events (for /review commands)
    elif object_kind == "note":
        note_type = payload.get("object_attributes", {}).get("noteable_type")
        note_body = payload.get("object_attributes", {}).get("note", "")
        
        if note_type == "MergeRequest" and "/review" in note_body.lower():
            project_id = payload["merge_request"]["target_project_id"]
            mr_iid = payload["merge_request"]["iid"]
            
            logger.info(f"Triggering review via comment for MR !{mr_iid}")
            background_tasks.add_task(process_merge_request, project_id, mr_iid)
            
            return JSONResponse({
                "status": "accepted",
                "message": f"Review queued for MR !{mr_iid}"
            })
        else:
            return JSONResponse({"status": "ignored"})
    
    else:
        logger.info(f"Ignoring event: {object_kind}")
        return JSONResponse({"status": "ignored", "reason": f"object_kind={object_kind}"})


@app.post("/test-review")
async def test_review(background_tasks: BackgroundTasks):
    """
    Trigger a test review using mock data.
    Useful for testing without actual GitLab webhooks.
    """
    logger.info("Test review endpoint called")
    
    background_tasks.add_task(process_merge_request, 1, 1, use_mock=True)
    
    return JSONResponse({
        "status": "accepted",
        "message": "Test review started. Check logs for progress.",
        "note": "Review will be saved to temp directory"
    })


@app.get("/config")
async def get_configuration():
    """Get current configuration (sanitized)."""
    config = get_config()
    return config.to_dict()


def main():
    """Entry point for running the application."""
    import uvicorn
    
    config = get_config()
    
    logger.info(f"Starting server on {config.host}:{config.port}")
    
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower()
    )


if __name__ == "__main__":
    main()
