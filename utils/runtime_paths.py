"""Resolve resources and writable paths before feature modules bind defaults."""
from dataclasses import dataclass
import os
from pathlib import Path
import sys


@dataclass(frozen=True)
class RuntimePaths:
    resources: Path
    workspace: Path
    standalone: bool

    @property
    def data(self):
        return self.workspace / "Data"

    @property
    def instance(self):
        return self.workspace / "instance"

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        source = Path(__file__).resolve().parents[1]
        resources = Path(getattr(sys, "_MEIPASS", source)).resolve()
        standalone = env.get("ENGCOST_STANDALONE") == "1"
        if standalone:
            configured = env.get("ENGCOST_WORKSPACE", "")
            if not configured or not Path(configured).is_absolute():
                raise ValueError("Standalone mode requires an absolute workspace")
            workspace = Path(configured).resolve()
            if workspace == resources or resources in workspace.parents:
                raise ValueError("Workspace must be outside application resources")
        else:
            workspace = source
        return cls(resources, workspace, standalone)

    def flask_config(self):
        if not self.standalone:
            return {}
        return {
            "APP_DATA_FILE": str(self.instance / "app_data.json"),
            "COSTING_DATA_ROOT": str(self.data),
            "COSTING_PERIOD_BINDINGS_FILE": str(self.instance / "costing_period_bindings.json"),
            "ENGCOST_STANDALONE": True,
        }
