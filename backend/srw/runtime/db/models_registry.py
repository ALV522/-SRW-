from __future__ import annotations

from srw.modules.audit import models as audit_models  # noqa: F401
from srw.modules.ai_runs import models as ai_run_models  # noqa: F401
from srw.modules.candidate import models as candidate_models  # noqa: F401
from srw.modules.decision import models as decision_models  # noqa: F401
from srw.modules.identity import models as identity_models  # noqa: F401
from srw.modules.calibration import models as calibration_models  # noqa: F401
from srw.modules.protocol import models as protocol_models  # noqa: F401
from srw.modules.recruiting import models as recruiting_models  # noqa: F401
from srw.modules.recruiting import operations_models as recruiting_operations_models  # noqa: F401
from srw.modules.feedback import models as feedback_models  # noqa: F401
from srw.modules.decision_operations import models as decision_operations_models  # noqa: F401
from srw.modules.planning import models as planning_models  # noqa: F401
from srw.modules.knowledge_governance import models as knowledge_governance_models  # noqa: F401
from srw.modules.recruitment_intelligence import models as recruitment_intelligence_models  # noqa: F401
from srw.modules.work import models as work_models  # noqa: F401
from srw.modules import fullworkbench as fullworkbench_models  # noqa: F401
from srw.runtime.jobs import models as job_models  # noqa: F401
from srw.supervisor import models as supervisor_models  # noqa: F401
from srw.runtime import settings as runtime_settings  # noqa: F401


def import_v1_models() -> None:
    """Register all v1 ORM models on V1Base metadata."""
