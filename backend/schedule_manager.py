"""
Schedule Manager
Tracks scheduled tool runs (one-time and recurring cron).
Persists to JSON on the shared volume.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


DATA_DIR = Path(os.environ.get("SESSION_DATA_DIR", "/opt/pentest/data/sessions"))
SCHEDULES_FILE = DATA_DIR / "schedules.json"


class ScheduledJob:
    def __init__(
        self,
        session_id: str,
        tool: str,
        parameters: dict,
        schedule_type: str,  # once | cron
        label: str = "",
        run_at: str = None,  # ISO str for once
        cron_expr: str = None,
        created_by: str = None,
        id: str = None,
    ):
        self.id = id or str(uuid.uuid4())[:12]
        self.session_id = session_id
        self.tool = tool
        self.parameters = parameters
        self.schedule_type = schedule_type
        self.run_at = run_at
        self.cron_expr = cron_expr
        self.label = label
        self.created_at = datetime.utcnow().isoformat()
        self.last_run: Optional[str] = None
        self.next_run: Optional[str] = run_at if schedule_type == "once" else None
        self.status = "scheduled"  # scheduled|running|completed|failed|disabled
        self.run_count = 0
        self.created_by = created_by

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "tool": self.tool,
            "parameters": self.parameters,
            "schedule_type": self.schedule_type,
            "run_at": self.run_at,
            "cron_expr": self.cron_expr,
            "label": self.label,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "status": self.status,
            "run_count": self.run_count,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledJob":
        job = cls(
            session_id=data["session_id"],
            tool=data["tool"],
            parameters=data.get("parameters", {}),
            schedule_type=data.get("schedule_type", "once"),
            label=data.get("label", ""),
            run_at=data.get("run_at"),
            cron_expr=data.get("cron_expr"),
            created_by=data.get("created_by"),
            id=data["id"],
        )
        job.created_at = data.get("created_at", job.created_at)
        job.last_run = data.get("last_run")
        job.next_run = data.get("next_run")
        job.status = data.get("status", "scheduled")
        job.run_count = data.get("run_count", 0)
        return job


class ScheduleManager:
    def __init__(self):
        self.jobs: dict[str, ScheduledJob] = {}
        self._load()

    def _load(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if SCHEDULES_FILE.exists():
            try:
                data = json.loads(SCHEDULES_FILE.read_text())
                for entry in data:
                    job = ScheduledJob.from_dict(entry)
                    self.jobs[job.id] = job
                if self.jobs:
                    print(f"[INFO] Loaded {len(self.jobs)} scheduled job(s) from disk")
            except Exception as e:
                print(f"[WARN] Failed to load schedules: {e}")

    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            SCHEDULES_FILE.write_text(
                json.dumps([j.to_dict() for j in self.jobs.values()], indent=2)
            )
        except Exception as e:
            print(f"[WARN] Failed to save schedules: {e}")

    def create(
        self,
        session_id: str,
        tool: str,
        parameters: dict,
        schedule_type: str,
        label: str = "",
        run_at: str = None,
        cron_expr: str = None,
        created_by: str = None,
    ) -> ScheduledJob:
        job = ScheduledJob(
            session_id=session_id,
            tool=tool,
            parameters=parameters,
            schedule_type=schedule_type,
            label=label,
            run_at=run_at,
            cron_expr=cron_expr,
            created_by=created_by,
        )
        self.jobs[job.id] = job
        self._save()
        return job

    def get(self, job_id: str) -> Optional[ScheduledJob]:
        return self.jobs.get(job_id)

    def list_all(self) -> list[ScheduledJob]:
        return list(self.jobs.values())

    def list_for_session(self, session_id: str) -> list[ScheduledJob]:
        return [j for j in self.jobs.values() if j.session_id == session_id]

    def update_status(self, job_id: str, status: str, last_run: str = None, next_run: str = None) -> Optional[ScheduledJob]:
        job = self.jobs.get(job_id)
        if not job:
            return None
        job.status = status
        if last_run:
            job.last_run = last_run
            job.run_count += 1
        if next_run is not None:
            job.next_run = next_run
        self._save()
        return job

    def disable(self, job_id: str) -> Optional[ScheduledJob]:
        job = self.jobs.get(job_id)
        if not job:
            return None
        job.status = "disabled"
        self._save()
        return job

    def enable(self, job_id: str) -> Optional[ScheduledJob]:
        job = self.jobs.get(job_id)
        if not job:
            return None
        job.status = "scheduled"
        self._save()
        return job

    def delete(self, job_id: str) -> bool:
        if job_id not in self.jobs:
            return False
        del self.jobs[job_id]
        self._save()
        return True
