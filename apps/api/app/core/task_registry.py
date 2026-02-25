"""Background task registry — tracks asyncio.Tasks for logging, cancellation, and cleanup."""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Registry for background asyncio tasks.

    - Logs exceptions from tasks that would otherwise be silently swallowed
    - Tracks active tasks for graceful shutdown
    - Supports cancellation by task name
    - Provides per-user task lookup
    """

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._task_meta: dict[str, dict] = {}  # name → {user_id, ...}

    def create_task(
        self,
        coro,
        *,
        name: str,
        user_id: Optional[int] = None,
    ) -> asyncio.Task:
        """Create and track a background task.

        Args:
            coro: The coroutine to run.
            name: Unique name (e.g., "extraction-<run_id>").
            user_id: Optional user who triggered the task.

        Returns:
            The created asyncio.Task.
        """
        task = asyncio.create_task(coro, name=name)
        self._tasks[name] = task
        self._task_meta[name] = {"user_id": user_id}
        task.add_done_callback(lambda t: self._on_task_done(t, name, user_id))
        logger.info(f"Background task created: '{name}' (user={user_id})")
        return task

    def _on_task_done(self, task: asyncio.Task, name: str, user_id: Optional[int]):
        self._tasks.pop(name, None)
        self._task_meta.pop(name, None)
        if task.cancelled():
            logger.info(f"Background task '{name}' was cancelled (user={user_id})")
        elif exc := task.exception():
            logger.error(
                f"Background task '{name}' failed (user={user_id}): {exc}",
                exc_info=exc,
            )
        else:
            logger.info(f"Background task '{name}' completed (user={user_id})")

    def cancel_task(self, name: str) -> bool:
        """Cancel a task by name. Returns True if the task was found and cancelled."""
        task = self._tasks.get(name)
        if task and not task.done():
            task.cancel()
            logger.info(f"Cancellation requested for task '{name}'")
            return True
        return False

    def get_user_tasks(self, user_id: int) -> list[dict]:
        """List active tasks for a specific user."""
        result = []
        for name, meta in self._task_meta.items():
            if meta.get("user_id") == user_id:
                task = self._tasks.get(name)
                result.append({
                    "name": name,
                    "done": task.done() if task else True,
                    "cancelled": task.cancelled() if task else False,
                })
        return result

    @property
    def active_tasks(self) -> dict[str, asyncio.Task]:
        return dict(self._tasks)

    async def cancel_all(self, timeout: float = 10.0):
        """Cancel all active tasks and wait for them to finish."""
        tasks = list(self._tasks.values())
        if not tasks:
            return
        logger.info(f"Cancelling {len(tasks)} background tasks...")
        for task in tasks:
            task.cancel()
        await asyncio.wait(tasks, timeout=timeout)
        logger.info("Background task cleanup complete")


task_registry = TaskRegistry()
