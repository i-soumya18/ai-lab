"""File system watcher using watchdog (inotify-backed on Linux/WSL2).

FileWatcher monitors configured directories and triggers goal tasks
when files are created or modified. Path configurations are loaded
from the `watched_paths` PostgreSQL table at startup.

The observer runs in a background thread (watchdog uses os.inotify).
Goal triggering is dispatched to the asyncio event loop via
asyncio.run_coroutine_threadsafe().
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

import structlog
from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = structlog.get_logger()


class _AILabEventHandler(FileSystemEventHandler):
    """watchdog event handler that fires goal tasks on file events."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        goal_executor: Any,
        db_factory: Any,
    ) -> None:
        super().__init__()
        self._loop = loop
        self._executor = goal_executor
        self._db_factory = db_factory

    def on_created(self, event: Any) -> None:
        if not event.is_directory:
            asyncio.run_coroutine_threadsafe(
                self._handle_file_event(event.src_path, "created"),
                self._loop,
            )

    def on_modified(self, event: Any) -> None:
        if not event.is_directory:
            asyncio.run_coroutine_threadsafe(
                self._handle_file_event(event.src_path, "modified"),
                self._loop,
            )

    async def _handle_file_event(self, path: str, event_type: str) -> None:
        """Check if any enabled watcher has a goal template for this path."""
        from sqlalchemy import text
        try:
            async with self._db_factory() as db:
                result = await db.execute(
                    text(
                        "SELECT id, path, trigger_goal_template, recursive "
                        "FROM watched_paths WHERE enabled=TRUE"
                    )
                )
                watchers = result.fetchall()

            for watcher in watchers:
                watched_path = watcher.path
                if watcher.recursive:
                    matches = Path(path).is_relative_to(Path(watched_path))
                else:
                    matches = Path(path).parent == Path(watched_path)

                if matches and watcher.trigger_goal_template:
                    template = watcher.trigger_goal_template
                    title = f"Auto: {event_type} — {Path(path).name}"
                    description = (
                        template.replace("{{path}}", path)
                        .replace("{file_path}", path)
                        .replace("{{event}}", event_type)
                        .replace("{event}", event_type)
                    )
                    logger.info("file_watcher.trigger", path=path, event_type=event_type,
                                watcher_id=str(watcher.id))
                    await self._trigger_goal(title, description, path)
        except Exception as exc:
            logger.error("file_watcher.handle_event_error", path=path, error=str(exc))

    async def _trigger_goal(self, title: str, description: str, path: str) -> None:
        """Create a new goal and start executing it."""
        from goals.goal_manager import GoalManager
        from goals.goal_planner import GoalPlanner

        try:
            async with self._db_factory() as db:
                planner = GoalPlanner(ollama_client=self._executor._orchestrator._ollama)
                tasks = await planner.plan(title=title, description=description)
                manager = GoalManager(db)
                goal = await manager.create(
                    title=title,
                    description=description,
                    tasks=tasks,
                    context={"triggered_by": "file_watcher", "file_path": path},
                )
            await self._executor.start(goal.id)
            logger.info("file_watcher.goal_created", goal_id=goal.id, title=title)
        except Exception as exc:
            logger.error("file_watcher.trigger_goal_error", title=title, error=str(exc))


class FileWatcher:
    """Manages a watchdog Observer that monitors configured filesystem paths.

    Usage:
        watcher = FileWatcher(loop, goal_executor, db_factory)
        await watcher.load_and_start()   # call at app startup
        watcher.stop()                    # call at app shutdown
        await watcher.add_path("/app/watched/docs", recursive=True, template="...")
        await watcher.remove_path("/app/watched/docs")
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        goal_executor: Any,
        db_factory: Any,
    ) -> None:
        self._loop = loop
        self._executor = goal_executor
        self._db_factory = db_factory
        self._observer: Observer | None = None
        self._handler = _AILabEventHandler(loop, goal_executor, db_factory)
        self._watched: dict[str, Any] = {}  # path → watchdog watch handle
        self._lock = threading.Lock()

    async def load_and_start(self) -> None:
        """Load enabled watchers from the DB and start the observer thread."""
        from sqlalchemy import text
        self._observer = Observer()
        try:
            async with self._db_factory() as db:
                result = await db.execute(
                    text("SELECT path, recursive FROM watched_paths WHERE enabled=TRUE")
                )
                rows = result.fetchall()
        except Exception as exc:
            logger.warning("file_watcher.load_error", error=str(exc))
            rows = []

        for row in rows:
            self._add_watch(row.path, row.recursive)

        self._observer.start()
        logger.info("file_watcher.started", watch_count=len(self._watched))

    def stop(self) -> None:
        """Stop the watchdog observer thread."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            logger.info("file_watcher.stopped")

    def _add_watch(self, path: str, recursive: bool = True) -> bool:
        """Register a path with the watchdog observer. Thread-safe."""
        with self._lock:
            if path in self._watched:
                return False
            if not Path(path).exists():
                logger.warning("file_watcher.path_not_found", path=path)
                return False
            if self._observer:
                handle = self._observer.schedule(self._handler, path, recursive=recursive)
                self._watched[path] = handle
                logger.info("file_watcher.path_added", path=path, recursive=recursive)
                return True
        return False

    def _remove_watch(self, path: str) -> bool:
        """Unregister a path from the watchdog observer. Thread-safe."""
        with self._lock:
            handle = self._watched.pop(path, None)
            if handle and self._observer:
                self._observer.unschedule(handle)
                logger.info("file_watcher.path_removed", path=path)
                return True
        return False

    async def add_path(self, path: str, recursive: bool = True, template: str | None = None) -> bool:
        """Add a path to DB watched_paths and register with the observer."""
        from sqlalchemy import text
        try:
            async with self._db_factory() as db:
                await db.execute(
                    text(
                        "INSERT INTO watched_paths (path, recursive, trigger_goal_template, enabled) "
                        "VALUES (:path, :recursive, :template, TRUE) "
                        "ON CONFLICT (path) DO UPDATE SET recursive=:recursive, "
                        "trigger_goal_template=:template, enabled=TRUE"
                    ),
                    {"path": path, "recursive": recursive, "template": template},
                )
                await db.commit()
        except Exception as exc:
            logger.error("file_watcher.add_path_db_error", path=path, error=str(exc))
            return False
        return self._add_watch(path, recursive)

    async def remove_path(self, path: str) -> bool:
        """Remove a path from DB watched_paths and unregister from the observer."""
        from sqlalchemy import text
        try:
            async with self._db_factory() as db:
                await db.execute(
                    text("UPDATE watched_paths SET enabled=FALSE WHERE path=:path"),
                    {"path": path},
                )
                await db.commit()
        except Exception as exc:
            logger.error("file_watcher.remove_path_db_error", path=path, error=str(exc))
        return self._remove_watch(path)
