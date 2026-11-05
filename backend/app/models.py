"""Import all ORM models here.

Alembic autogenerate reads ``Base.metadata``, which only knows about a table
once its module has been imported. Adding a model without registering it here
silently produces a migration that drops the table.
"""

from __future__ import annotations

from app.modules.analytics import models as analytics_models  # noqa: F401
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.automation import models as automation_models  # noqa: F401
from app.modules.businesses import models as businesses_models  # noqa: F401
from app.modules.crm import models as crm_models  # noqa: F401
from app.modules.discovery import models as discovery_models  # noqa: F401
from app.modules.email import models as email_models  # noqa: F401
from app.modules.exports import models as exports_models  # noqa: F401
from app.modules.notifications import models as notifications_models  # noqa: F401
from app.modules.services_catalog import models as services_models  # noqa: F401
from app.modules.social import models as social_models  # noqa: F401
from app.modules.sources import models as sources_models  # noqa: F401
from app.modules.startups import models as startups_models  # noqa: F401
from app.modules.verified_prospecting import models as verified_prospecting_models  # noqa: F401
