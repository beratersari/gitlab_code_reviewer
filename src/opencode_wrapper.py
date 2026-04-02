"""
Opencode CLI wrapper for Python integration.
Handles repository cloning and code review execution.
"""

import subprocess
import tempfile
import os
import shutil
import asyncio
import uuid
import re
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

from logger import get_logger, log_flow_step
from config import get_config

logger = get_logger(__name__)

# Platform detection
IS_WINDOWS = platform.system() == "Windows"


@dataclass
class AgentTask:
    """Represents an agent task to be executed."""
    description: str
    prompt: str
    agent: str = "build"
    category: Optional[str] = None
    issue_key: Optional[str] = None  # For MR/issue tracking in session file names
    session_id: Optional[str] = None
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    skills: List[str] = field(default_factory=list)
    model: Optional[str] = None  # Model override (e.g. for code review with a free model)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "agent": self.agent,
            "category": self.category,
            "prompt": self.prompt,
            "skills": self.skills,
            "session_id": self.session_id,
        }


class AgentRunner:
    """Runs agents using Opencode CLI with async subprocess."""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.config = get_config()
        self.project_root = project_root or Path.cwd()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._opencode_cli = self._detect_opencode_cli()
    
    def _detect_opencode_cli(self) -> str:
        """Detect how to run opencode CLI."""
        # Check if opencode is directly available
        try:
            result = subprocess.run(
                ["opencode", "--version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return "opencode"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Check if bunx oh-my-opencode is available
        try:
            result = subprocess.run(
                ["bunx", "oh-my-opencode", "--version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return "bunx oh-my-opencode"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Default to opencode and let it fail gracefully if not installed
        logger.warning("Could not detect opencode CLI, defaulting to 'opencode'")
        return "opencode"
    
    def _build_command(self, task: AgentTask, session_file: Path) -> List[str]:
        """Build the opencode CLI command as a list (cross-platform).
        
        Command format: opencode run [options] <message>
        The message must be the last argument.
        
        Returns:
            List of command arguments for use with subprocess (no shell needed)
        """
        # Build base command
        cmd_parts = self._opencode_cli.split() + ["run"]
        
        # Add agent option
        cmd_parts.extend(["--agent", task.agent])
        
        # Use task-specific model if provided, otherwise default
        effective_model = task.model or self.config.opencode_model
        cmd_parts.extend(["--model", effective_model])
        
        # Add session continuation if specified
        if task.session_id:
            cmd_parts.extend(["--session-id", task.session_id])
        
        # Add the prompt as the final argument
        cmd_parts.append(task.prompt)
        
        return cmd_parts
    
    def _parse_progress(self, line: str) -> Optional[int]:
        """Parse progress percentage from agent output.

        Looks for patterns like:
        - "Progress: 75%"
        - "[███████░░░] 70%"
        - "Completed: 8/10 tasks (80%)"
        """
        # Pattern 1: Direct percentage (e.g., "Progress: 75%" or "75%")
        match = re.search(r'(\d+)%', line)
        if match:
            return int(match.group(1))

        # Pattern 2: Progress bar blocks
        # Count filled vs empty blocks
        filled_blocks = line.count('█') + line.count('▓') + line.count('■')
        empty_blocks = line.count('░') + line.count('▒') + line.count(' ')
        total_blocks = filled_blocks + empty_blocks
        if total_blocks >= 5 and filled_blocks > 0:
            return int((filled_blocks / total_blocks) * 100)

        # Pattern 3: Completed tasks (e.g., "Completed: 8/10 tasks")
        match = re.search(r'(\d+)\s*/\s*(\d+)\s*(?:tasks|steps|items)', line, re.IGNORECASE)
        if match:
            completed, total = int(match.group(1)), int(match.group(2))
            if total > 0:
                return int((completed / total) * 100)

        return None
    
    def _parse_session_id(self, lines: List[str]) -> Optional[str]:
        """Parse opencode session ID from output lines.

        Looks for patterns like:
        - "Session: ses_abc123" (actual format from opencode)
        - "Session ID: ses_abc123"
        - "session: ses_abc123"
        """
        # Actual format seen in logs: "Session: ses_2c996b381ffe22SXIwktVa9kc7"
        patterns = [
            r'Session[:]\s+(ses_[a-zA-Z0-9_-]+)',
            r'Session\s*ID[:]\s+(ses_[a-zA-Z0-9_-]+)',
            r'session[:]\s+(ses_[a-zA-Z0-9_-]+)',
        ]

        for line in lines:
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(1)

        return None
    
    def _get_session_file(
        self,
        task_id: str,
        issue_key: Optional[str] = None,
        attempt_number: int = 0,
    ) -> Path:
        """Get path to session output file.

        Args:
            task_id: The task ID
            issue_key: The issue key (e.g., "MR-1")
            attempt_number: The retry attempt number (0 = first attempt)

        Returns:
            Path to the session log file

        Naming convention:
            - First attempt: MR-1_20240327_143052_0.log
            - Retry 1: MR-1_20240327_143052_1.log
            - Retry 2: MR-1_20240327_143052_2.log
        """
        # Ensure directory exists
        sessions_dir = Path(self.config.temp_dir) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        if issue_key:
            # Format: ISSUEKEY_DATETIME_RETRYCOUNT.log
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{issue_key}_{timestamp}_{attempt_number}.log"
        else:
            # Fallback to task_id if no issue_key provided
            filename = f"{task_id}_{attempt_number}.log"

        path = sessions_dir / filename
        return path
    
    async def run_agent(
        self,
        task: AgentTask,
        on_output: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        timeout_seconds: Optional[int] = None,
        attempt_number: int = 0,
    ) -> Dict[str, Any]:
        """Run an agent task asynchronously with streaming output.

        Args:
            task: The agent task to run
            on_output: Callback for output lines (stream, line)
            on_complete: Callback when complete (result)
            on_progress: Callback for progress updates (percentage, message)
            timeout_seconds: Override timeout from config
            attempt_number: The retry attempt number (0 = first attempt)

        Returns:
            Dict with task result including stdout, stderr, returncode, session_file
        """
        effective_timeout = timeout_seconds or self.config.opencode_timeout
        start_time = asyncio.get_event_loop().time()

        # Create session file for this task
        session_file = self._get_session_file(
            task.task_id,
            issue_key=task.issue_key,
            attempt_number=attempt_number,
        )
        session_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Build the command as a list (cross-platform)
        cmd_list = self._build_command(task, session_file)
        
        logger.info(f"Starting agent task {task.task_id}", extra={
            'cmd': ' '.join(cmd_list[:5]) + '...',
            'timeout': effective_timeout,
            'model': task.model or self.config.opencode_model,
            'session_file': str(session_file),
            'attempt_number': attempt_number,
        })
        
        # Open session file for writing output
        with open(session_file, 'w', encoding='utf-8') as session_fh:
            # Run the process using exec (no shell) for cross-platform compatibility
            try:
                if IS_WINDOWS:
                    # Windows: use CREATE_NEW_PROCESS_GROUP for proper termination
                    process = await asyncio.create_subprocess_exec(
                        *cmd_list,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=self.project_root,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
                    )
                else:
                    # Unix/Linux/Mac
                    process = await asyncio.create_subprocess_exec(
                        *cmd_list,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=self.project_root,
                    )
                
                # Close stdin immediately to signal EOF - tells opencode we're done sending input
                if process.stdin:
                    process.stdin.close()
                    await process.stdin.wait_closed()
            except Exception as e:
                logger.error(f"Failed to start subprocess: {e}")
                return {
                    "task_id": task.task_id,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"Failed to start opencode: {e}",
                    "session_file": str(session_file),
                    "timed_out": False,
                }
            
            stdout_lines = []
            stderr_lines = []
            last_progress = 0
            last_output_time = start_time
            
            # Read output streams with progress tracking and timeout check
            async def read_stream(stream, lines, callback_name, file_handle):
                nonlocal last_progress, last_output_time
                while True:
                    # Check timeout
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > effective_timeout:
                        raise asyncio.TimeoutError(
                            f"Task exceeded timeout of {effective_timeout} seconds"
                        )

                    try:
                        line = await asyncio.wait_for(
                            stream.readline(),
                            timeout=1.0  # 1 second check interval
                        )
                    except asyncio.TimeoutError:
                        # No data available - check if we should stop
                        # If no output for 5 seconds and we have content, consider it done
                        time_since_output = asyncio.get_event_loop().time() - last_output_time
                        if time_since_output > 5.0 and len(lines) > 0:
                            logger.debug(f"No output for {time_since_output:.1f}s, considering stream complete")
                            break
                        continue

                    if not line:
                        break
                    
                    last_output_time = asyncio.get_event_loop().time()
                    decoded = line.decode('utf-8', errors='replace').rstrip()
                    lines.append(decoded)

                    # Write to session file
                    file_handle.write(decoded + '\n')
                    file_handle.flush()

                    # Parse progress from output
                    progress = self._parse_progress(decoded)
                    if progress and progress != last_progress:
                        last_progress = progress
                        if on_progress:
                            on_progress(progress, decoded[:100])

                    if on_output:
                        on_output(callback_name, decoded)

            try:
                # Wait for completion with timeout
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_lines, "stdout", session_fh),
                        read_stream(process.stderr, stderr_lines, "stderr", session_fh),
                    ),
                    timeout=effective_timeout
                )
                
                # Wait for process to exit with a shorter timeout
                # Some processes (like opencode) may keep running even after closing stdout
                try:
                    returncode = await asyncio.wait_for(process.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Process didn't exit after streams closed, force terminate
                    logger.warning(f"Process didn't exit gracefully after output completed, terminating...")
                    try:
                        process.terminate()
                        returncode = await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                        returncode = await process.wait()
                        
            except asyncio.TimeoutError:
                # Kill the process on timeout
                try:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except Exception:
                    pass
                # Extract session ID from output collected so far
                all_output_lines = stdout_lines + stderr_lines
                session_id = self._parse_session_id(all_output_lines)
                error_msg = f"Task exceeded timeout of {effective_timeout} seconds"
                logger.error(error_msg)
                return {
                    "task_id": task.task_id,
                    "returncode": -1,
                    "stdout": "\n".join(stdout_lines),
                    "stderr": f"\n[TIMEOUT] {error_msg}",
                    "session_file": str(session_file),
                    "opencode_session_id": session_id,
                    "progress": last_progress,
                    "timed_out": True,
                }
        
        # Extract session ID from output
        all_output_lines = stdout_lines + stderr_lines
        session_id = self._parse_session_id(all_output_lines)

        result = {
            "task_id": task.task_id,
            "returncode": returncode,
            "stdout": "\n".join(stdout_lines),
            "stderr": "\n".join(stderr_lines),
            "session_file": str(session_file),
            "opencode_session_id": session_id,
            "progress": 100 if returncode == 0 else last_progress,
            "timed_out": False,
        }

        if on_complete:
            on_complete(result)

        logger.info(f"Agent task {task.task_id} completed with returncode {returncode}")

        return result
    
    async def run_agent_with_retry(
        self,
        task: AgentTask,
        on_output: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        on_retry: Optional[Callable] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run an agent task with automatic retry on failure.

        Args:
            task: The agent task to run
            on_output: Callback for output lines (stream, line)
            on_complete: Callback when complete (result)
            on_progress: Callback for progress updates (percentage, message)
            on_retry: Callback when a retry is attempted (attempt_number, delay_seconds, reason, session_file)
            timeout_seconds: Override timeout from config
            max_retries: Override max retries from config

        Returns:
            Dict with task result including retry information and all session files
        """
        effective_max_retries = max_retries or getattr(self.config, 'agent_task_max_retries', 2)
        retry_delay = getattr(self.config, 'agent_task_retry_delay_seconds', 5)
        backoff_multiplier = getattr(self.config, 'agent_task_retry_backoff_multiplier', 2)
        retry_on_timeout = getattr(self.config, 'agent_task_retry_on_timeout', True)
        retry_on_error = getattr(self.config, 'agent_task_retry_on_error', True)

        last_result = None
        last_session_id = None
        attempt = 0
        all_session_files = []

        while attempt <= effective_max_retries:
            # Run the task with attempt number (0 = first attempt, 1+ = retries)
            result = await self.run_agent(
                task,
                on_output=on_output,
                on_complete=on_complete,
                on_progress=on_progress,
                timeout_seconds=timeout_seconds,
                attempt_number=attempt,
            )

            # Track session file and opencode session ID for this attempt
            if result.get("session_file"):
                all_session_files.append(result["session_file"])
            if result.get("opencode_session_id"):
                last_session_id = result["opencode_session_id"]

            # Check if successful
            if result.get("returncode") == 0:
                result["retry_info"] = {
                    "attempts": attempt + 1,
                    "max_retries": effective_max_retries,
                    "retried": attempt > 0,
                    "all_session_files": all_session_files,
                    "last_opencode_session_id": last_session_id,
                }
                return result

            # Determine if we should retry
            should_retry = False
            retry_reason = ""

            if result.get("timed_out"):
                if retry_on_timeout and attempt < effective_max_retries:
                    should_retry = True
                    retry_reason = "timeout"
            elif retry_on_error and attempt < effective_max_retries:
                should_retry = True
                retry_reason = "error"

            if should_retry:
                attempt += 1

                # Calculate delay with exponential backoff
                delay = retry_delay * (backoff_multiplier ** (attempt - 1))

                # Extract error details from the failed attempt
                error_message = result.get("stderr", "") if result.get("returncode") != 0 else None
                return_code = result.get("returncode")

                if on_retry:
                    on_retry(attempt, delay, retry_reason, result.get("session_file"), error_message, return_code, result.get("opencode_session_id"))

                # Log retry attempt
                logger.warning(f"{retry_reason.capitalize()} on attempt {attempt}/{effective_max_retries} for {task.task_id}, retrying in {delay:.1f}s...")

                # Wait before retry
                await asyncio.sleep(delay)

                # Create new task ID for retry
                task.task_id = f"task_{uuid.uuid4().hex[:8]}"

                last_result = result
            else:
                # No more retries - include session ID from last attempt
                result["retry_info"] = {
                    "attempts": attempt + 1,
                    "max_retries": effective_max_retries,
                    "retried": attempt > 0,
                    "final_failure": True,
                    "all_session_files": all_session_files,
                    "last_opencode_session_id": last_session_id,
                }
                return result

        # Should not reach here, but just in case
        if last_result:
            last_result["retry_info"] = {
                "attempts": attempt + 1,
                "max_retries": effective_max_retries,
                "retried": True,
                "final_failure": True,
                "all_session_files": all_session_files,
                "last_opencode_session_id": last_session_id,
            }
            return last_result

        return {
            "task_id": task.task_id,
            "returncode": -1,
            "stdout": "",
            "stderr": "Max retries exceeded",
            "session_file": all_session_files[-1] if all_session_files else None,
            "opencode_session_id": last_session_id,
            "retry_info": {
                "attempts": attempt + 1,
                "max_retries": effective_max_retries,
                "retried": True,
                "final_failure": True,
                "all_session_files": all_session_files,
                "last_opencode_session_id": last_session_id,
            },
        }


@dataclass
class ReviewResult:
    """Result of a code review."""
    file_path: str
    review_text: str
    success: bool
    error_message: Optional[str] = None


class OpencodeReviewer:
    """Handles code review using opencode CLI."""
    
    def __init__(self, repo_path: Path, model: Optional[str] = None, 
                 issue_key: Optional[str] = None, use_retry: bool = False):
        """
        Initialize the code reviewer.
        
        Args:
            repo_path: Path to the repository to review
            model: Model to use for review (defaults to config)
            issue_key: Issue/MR key for session file naming (e.g., "MR-123")
            use_retry: Whether to use retry mechanism on failure
        """
        self.config = get_config()
        self.repo_path = Path(repo_path)
        self.model = model or self.config.opencode_model
        self.issue_key = issue_key
        self.use_retry = use_retry
        self.review_rules = self._load_review_rules()
        
        log_flow_step(logger, "reviewer_init", {
            'repo_path': str(repo_path),
            'model': self.model,
            'has_rules': bool(self.review_rules),
            'issue_key': issue_key,
            'use_retry': use_retry
        })
    
    def _load_review_rules(self) -> str:
        """Load project-specific review rules if they exist."""
        rules_path = self.repo_path / "agent" / "rules" / "CODE_REVIEW.md"
        
        if rules_path.exists():
            try:
                with open(rules_path, 'r') as f:
                    content = f.read()
                logger.info(f"Loaded review rules from: {rules_path}")
                return content
            except Exception as e:
                logger.warning(f"Failed to load review rules: {e}")
                return ""
        else:
            logger.info(f"No review rules found at: {rules_path}")
            return ""
    
    def _build_review_prompt(self, file_path: str, diff_content: str, 
                            file_content: Optional[str] = None) -> str:
        """Construct review prompt with project rules."""
        
        rules_section = ""
        if self.review_rules:
            rules_section = f"""
## Project Review Rules (CRITICAL - FOLLOW STRICTLY)
The following rules are specific to this project and MUST be followed in your review:

{self.review_rules}

---
"""
        
        full_content_section = ""
        if file_content:
            full_content_section = f"""
## Full File Content (for context)
```python
{file_content}
```
"""
        
        return f"""You are an expert code reviewer. Review the following code changes carefully.

{rules_section}

## File to Review
Path: `{file_path}`

## Changes (Diff)
```diff
{diff_content}
```
{full_content_section}

## Review Instructions

Please provide a comprehensive code review that includes:

1. **Summary**: Brief overview of what the code does and your overall assessment

2. **Issues Found**: List specific issues with:
   - Severity (Critical/High/Medium/Low)
   - Line numbers where applicable
   - Detailed explanation of the problem
   - Suggested fix with code example

3. ** adherence to Project Rules**: Check compliance with the Project Review Rules above

4. **Positive Aspects**: Highlight good practices you notice

5. **Recommendations**: Suggestions for improvement (not necessarily issues)

Format your response in Markdown with clear sections. Be specific and actionable.
If the code looks good and follows all rules, explicitly state "**LGTM**" (Looks Good To Me).
"""
    
    async def review_file_async(self, file_path: str, diff_content: str,
                                 file_content: Optional[str] = None) -> ReviewResult:
        """Review a single file using opencode CLI asynchronously."""
        
        log_flow_step(logger, "review_file_start", {
            'file_path': file_path,
            'diff_lines': len(diff_content.splitlines()),
            'has_full_content': bool(file_content),
            'issue_key': self.issue_key
        })
        
        # Build the review prompt
        prompt = self._build_review_prompt(file_path, diff_content, file_content)
        
        # Create agent task with issue_key for session file naming
        task = AgentTask(
            description=f"Review {file_path}",
            prompt=prompt,
            agent="build",
            model=self.model,
            issue_key=self.issue_key
        )
        
        # Create agent runner
        runner = AgentRunner(project_root=self.repo_path)
        
        try:
            # Run the agent (with or without retry)
            if self.use_retry:
                result = await runner.run_agent_with_retry(task)
            else:
                result = await runner.run_agent(task)
            
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            returncode = result.get("returncode", -1)
            timed_out = result.get("timed_out", False)
            session_file = result.get("session_file")
            opencode_session_id = result.get("opencode_session_id")
            
            # Log session info
            if session_file:
                logger.info(f"Session output saved to: {session_file}")
            if opencode_session_id:
                logger.info(f"Opencode session ID: {opencode_session_id}")
            
            # Check for timeout
            if timed_out:
                error_msg = f"Opencode review timed out after {self.config.opencode_timeout}s"
                logger.error(error_msg)
                return ReviewResult(
                    file_path=file_path,
                    review_text="",
                    success=False,
                    error_message=error_msg
                )
            
            # Use stdout as review text
            review_text = stdout
            
            # Check for errors - but be lenient if we got output
            if returncode != 0 and not review_text.strip():
                error_msg = f"Opencode failed with code {returncode}: {stderr}"
                logger.error(error_msg)
                return ReviewResult(
                    file_path=file_path,
                    review_text="",
                    success=False,
                    error_message=error_msg
                )
            
            # Log warning if exit code is non-zero but we have output
            if returncode != 0:
                logger.warning(f"Opencode returned non-zero exit code {returncode} but produced output")
                if stderr:
                    logger.debug(f"Opencode stderr: {stderr}")
            
            log_flow_step(logger, "review_file_complete", {
                'file_path': file_path,
                'review_length': len(review_text),
                'success': True,
                'session_file': session_file,
                'opencode_session_id': opencode_session_id
            })
            
            return ReviewResult(
                file_path=file_path,
                review_text=review_text,
                success=True
            )
            
        except Exception as e:
            error_msg = f"Unexpected error during review: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return ReviewResult(
                file_path=file_path,
                review_text="",
                success=False,
                error_message=error_msg
            )
    
    def review_file(self, file_path: str, diff_content: str,
                   file_content: Optional[str] = None) -> ReviewResult:
        """Review a single file using opencode CLI (sync wrapper)."""
        # Run the async version in the current event loop or create a new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new loop in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.review_file_async(file_path, diff_content, file_content)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.review_file_async(file_path, diff_content, file_content)
                )
        except RuntimeError:
            # No event loop running, create a new one
            return asyncio.run(
                self.review_file_async(file_path, diff_content, file_content)
            )
    
    def review_files(self, files: List[tuple]) -> List[ReviewResult]:
        """
        Review multiple files.
        
        Args:
            files: List of tuples (file_path, diff_content, optional_file_content)
            
        Returns:
            List of ReviewResult objects
        """
        results = []
        
        for i, file_data in enumerate(files, 1):
            if len(file_data) == 2:
                file_path, diff_content = file_data
                file_content = None
            else:
                file_path, diff_content, file_content = file_data
            
            logger.info(f"Reviewing file {i}/{len(files)}: {file_path}")
            result = self.review_file(file_path, diff_content, file_content)
            results.append(result)
        
        return results


class RepositoryCloner:
    """Handles cloning of GitLab repositories."""
    
    def __init__(self, temp_dir: Optional[Path] = None):
        self.config = get_config()
        self.temp_dir = temp_dir or self.config.temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Repository cloner initialized with temp dir: {self.temp_dir}")
    
    def clone(self, repo_url: str, branch: str, 
              token: Optional[str] = None) -> Path:
        """
        Clone a repository to a temporary location.
        
        Args:
            repo_url: Repository URL (HTTPS)
            branch: Branch to checkout
            token: Optional access token for private repos
            
        Returns:
            Path to cloned repository
        """
        # Create unique directory name
        import uuid
        clone_dir = self.temp_dir / f"repo_{uuid.uuid4().hex[:8]}"
        
        log_flow_step(logger, "clone_start", {
            'repo_url': repo_url.replace(token or '', '***') if token else repo_url,
            'branch': branch,
            'dest': str(clone_dir)
        })
        
        try:
            # Insert token into URL if provided
            if token and repo_url.startswith("https://"):
                repo_url = repo_url.replace("https://", f"https://oauth2:{token}@")
            
            # Clone with minimal depth for speed
            cmd = [
                "git", "clone",
                "--depth", "1",
                "--branch", branch,
                "--single-branch",
                repo_url,
                str(clone_dir)
            ]
            
            logger.debug(f"Running git clone command")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Git clone failed: {result.stderr}")
            
            log_flow_step(logger, "clone_complete", {
                'dest': str(clone_dir),
                'size_mb': self._get_dir_size(clone_dir)
            })
            
            return clone_dir
            
        except Exception as e:
            # Clean up on failure
            if clone_dir.exists():
                shutil.rmtree(clone_dir)
            logger.error(f"Clone failed: {e}")
            raise
    
    def cleanup(self, repo_path: Path):
        """Remove cloned repository."""
        if repo_path.exists():
            shutil.rmtree(repo_path)
            logger.info(f"Cleaned up repository: {repo_path}")
    
    def _get_dir_size(self, path: Path) -> float:
        """Get directory size in MB."""
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = Path(dirpath) / f
                total += fp.stat().st_size
        return round(total / (1024 * 1024), 2)
