"""
engine/checkpoint.py - Step-Wise Crash-Proof Checkpoint & Auto-Resume Manager
Persists intermediate artifacts (`fact_sheet.json`, `script.json`, `storyboard.json`,
voice audio tracks, visual assets, rendered scenes) in `work_dir` (Google Drive on Colab)
so mobile browser disconnects never lose progress or duplicate API/GPU compute.
"""
import json
import os
import time
from typing import Any, Dict, Optional


class CheckpointManager:
    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        os.makedirs(self.work_dir, exist_ok=True)
        self.state_path = os.path.join(self.work_dir, "checkpoint_state.json")
        self.state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {"completed_stages": [], "artifacts": {}, "updated_at": time.time()}

    def save(self) -> None:
        self.state["updated_at"] = time.time()
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def mark_stage_done(self, stage_name: str, artifact_path: Optional[str] = None) -> None:
        stages = self.state.setdefault("completed_stages", [])
        if stage_name not in stages:
            stages.append(stage_name)
        if artifact_path:
            self.state.setdefault("artifacts", {})[stage_name] = artifact_path
        self.save()

    def is_stage_done(self, stage_name: str, verify_file: Optional[str] = None) -> bool:
        if stage_name not in self.state.get("completed_stages", []):
            return False
        target = verify_file or self.state.get("artifacts", {}).get(stage_name)
        if target:
            return os.path.exists(target) and os.path.getsize(target) > 100
        return True
