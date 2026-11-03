"""The import and export API.

Two surfaces: what the account can export, and what it can import. Both are
background work with a row that records what was asked for and what came out.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, Response, UploadFile

from app.core.audit import client_ip, record_audit
from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionDep
from app.core.exceptions import (
    NotFoundError,
    TooManyRequestsError,
    ValidationFailedError,
)
from app.core.logging import get_logger
from app.core.ratelimit import RateLimitRule, get_rate_limiter
from app.integrations.storage import StorageError, get_storage
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.exports import importer, service
from app.modules.exports.formats import (
    EXPORT_FORMATS,
    FORMAT_EXTENSIONS,
    FORMAT_MEDIA_TYPES,
    count_rows,
    read_header,
)
from app.modules.exports.models import ExportJob, ImportJob
from app.modules.exports.schemas import (
    ExportCatalogueOut,
    ExportJobListOut,
    ExportJobOut,
    ExportModuleOut,
    ExportRequestIn,
    ImportJobListOut,
    ImportJobOut,
    ImportRunIn,
    ImportUploadOut,
    ImportVocabularyOut,
)

exports_router = APIRouter(prefix="/exports", tags=["exports"])
imports_router = APIRouter(prefix="/imports", tags=["imports"])

logger = get_logger(__name__)

Csrf = Depends(require_csrf_for_state_changes())

EXPORT_RULE = RateLimitRule(max_attempts=20, window_seconds=300)
IMPORT_RULE = RateLimitRule(max_attempts=5, window_seconds=3600)

# The formats an upload may arrive in, and the extension each one is stored
# under. The extension is decided here, never taken from the client.
_UPLOAD_FORMATS: dict[str, str] = {"csv": "csv", "xlsx": "xlsx"}
_UPLOAD_EXTENSIONS: dict[str, str] = {".csv": "csv", ".xlsx": "xlsx"}


def _rate_limit(scope: str, actor: str, rule: RateLimitRule, message: str) -> None:
    allowed, retry_after = get_rate_limiter().check(scope, actor, rule)
    if not allowed:
        raise TooManyRequestsError(
            message,
            headers={"Retry-After": str(int(retry_after))},
            details={"retry_after_seconds": int(retry_after)},
        )


def _export_out(job: ExportJob) -> ExportJobOut:
    return ExportJobOut(
        id=job.id,
        module=job.module,
        export_format=job.export_format,
        status=job.status,
        filters=dict(job.filters or {}),
        selected_fields=list(job.selected_fields or []),
        total_records=job.total_records,
        error_details=job.error_details,
        created_at=job.created_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        downloadable=bool(job.storage_key) and job.status == "completed",
    )


def _import_out(
    job: ImportJob,
    *,
    columns: list[str] | None = None,
    suggested: dict[str, str] | None = None,
) -> ImportJobOut:
    return ImportJobOut(
        id=job.id,
        file_name=job.file_name,
        file_format=job.file_format,
        status=job.status,
        columns=columns or [],
        suggested_mapping=suggested or {},
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        failed_rows=job.failed_rows,
        error_details=job.error_details,
        created_at=job.created_at,
        completed_at=job.completed_at,
        mapping_config=dict(job.mapping_config or {}),
    )


@exports_router.get("/catalogue", response_model=ExportCatalogueOut)
async def export_catalogue() -> ExportCatalogueOut:
    """What can be exported, in which formats, with which filters."""
    modules = [
        ExportModuleOut(
            key=spec.key,
            label=spec.label,
            filters=list(spec.filter_keys),
            columns=list(service.columns_for(spec.key)),
            boolean_filters=list(spec.boolean_filters),
            numeric_filters=list(spec.numeric_filters),
        )
        for spec in service.EXPORT_MODULES.values()
    ]
    return ExportCatalogueOut(modules=modules, formats=list(EXPORT_FORMATS))


@exports_router.get("", response_model=ExportJobListOut)
async def list_exports(
    session: AsyncSessionDep, user: CurrentUser, limit: int = 50
) -> ExportJobListOut:
    jobs = await service.list_export_jobs(session, user.id, limit=limit)
    return ExportJobListOut(items=[_export_out(job) for job in jobs], total=len(jobs))


@exports_router.post("", response_model=ExportJobOut, status_code=201, dependencies=[Csrf])
async def create_export(
    request: Request,
    payload: ExportRequestIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> ExportJobOut:
    """Queue an export and say how it was handed to the runner."""
    _rate_limit("export_create", str(user.id), EXPORT_RULE, "Too many exports requested.")

    job = await service.create_export_job(
        session,
        owner_user_id=user.id,
        module=payload.module,
        export_format=payload.format,
        filters=payload.filters,
        selected_fields=payload.selected_fields,
    )
    await record_audit(
        session,
        action="export.create",
        owner_user_id=user.id,
        entity_type="export_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={
            "module": job.module,
            "format": job.export_format,
            "fields": list(job.selected_fields or []),
        },
    )
    mode = await service.dispatch_export(session, job, background_tasks)
    logger.info("export_dispatched", job_id=str(job.id), mode=mode)
    return _export_out(job)


@exports_router.get("/{job_id}", response_model=ExportJobOut)
async def export_detail(
    job_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ExportJobOut:
    job = await service.get_export_job(session, user.id, job_id)
    return _export_out(job)


@exports_router.get("/{job_id}/download", response_class=Response)
async def download_export(
    request: Request,
    job_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> Response:
    """The file this export produced."""
    job = await service.get_export_job(session, user.id, job_id)
    if job.status != "completed":
        raise ValidationFailedError(
            f"This export is '{job.status}' and has no file to download",
            details={"status": job.status},
        )
    try:
        data = service.read_export_file(job, settings=settings)
    except StorageError as exc:
        raise NotFoundError("This export's file is no longer available") from exc

    await record_audit(
        session,
        action="export.download",
        owner_user_id=user.id,
        entity_type="export_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={"module": job.module, "format": job.export_format},
    )
    extension = FORMAT_EXTENSIONS.get(job.export_format, "csv")
    # The filename is built here, never taken from a stored name: a header value
    # is not a place to put a user-supplied string.
    filename = f"sparkxflow-{job.module}-{job.id}.{extension}"
    return Response(
        content=data,
        media_type=FORMAT_MEDIA_TYPES.get(job.export_format, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@exports_router.delete("/{job_id}", response_model=ExportJobOut, dependencies=[Csrf])
async def delete_export(
    request: Request,
    job_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> ExportJobOut:
    """Remove the file. The row keeps the history of what was exported."""
    job = await service.get_export_job(session, user.id, job_id)
    if job.storage_key:
        storage = get_storage(settings)
        try:
            storage.delete(job.storage_key)
        except StorageError as exc:
            # The row still clears its pointer: the file is already unreachable,
            # and refusing to release it would leave the row claiming a file
            # that is not there.
            logger.warning(
                "export_file_delete_failed", job_id=str(job.id), error_type=type(exc).__name__
            )
    job.storage_key = None
    await record_audit(
        session,
        action="export.delete",
        owner_user_id=user.id,
        entity_type="export_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={"module": job.module},
    )
    return _export_out(job)


@imports_router.get("/vocabulary", response_model=ImportVocabularyOut)
async def import_vocabulary() -> ImportVocabularyOut:
    """The fields an import understands, and the duplicate strategies offered."""
    return ImportVocabularyOut(
        fields=[
            {"key": key, "label": label} for key, label in importer.IMPORT_FIELDS.items()
        ],
        duplicate_strategies=list(importer.DUPLICATE_STRATEGIES),
        formats=list(_UPLOAD_FORMATS),
    )


@imports_router.get("", response_model=ImportJobListOut)
async def list_imports(
    session: AsyncSessionDep, user: CurrentUser, limit: int = 50
) -> ImportJobListOut:
    jobs = await importer.list_import_jobs(session, user.id, limit=limit)
    return ImportJobListOut(items=[_import_out(job) for job in jobs], total=len(jobs))


@imports_router.post("", response_model=ImportUploadOut, status_code=201, dependencies=[Csrf])
async def upload_import(
    request: Request,
    session: AsyncSessionDep,
    user: CurrentUser,
    settings: Settings = Depends(get_settings),
    file: UploadFile = File(...),
) -> ImportUploadOut:
    """Take the file, read its shape, and wait for a confirmed mapping.

    Nothing is written here. The operator sees the columns, confirms what each
    one means, and only then does the import run.
    """
    _rate_limit("import_create", str(user.id), IMPORT_RULE, "Too many imports uploaded.")

    file_name = (file.filename or "upload").strip()[:255]
    extension = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    file_format = _UPLOAD_EXTENSIONS.get(extension)
    if file_format is None:
        raise ValidationFailedError(
            "Only .csv and .xlsx files can be imported",
            details={"accepted": sorted(_UPLOAD_EXTENSIONS)},
        )

    data = await file.read()
    if len(data) > settings.max_import_file_bytes:
        raise ValidationFailedError(
            f"That file is larger than the {settings.max_import_file_bytes} byte limit"
        )
    if not data:
        raise ValidationFailedError("That file is empty")

    header = read_header(data, file_format)
    if not header:
        raise ValidationFailedError("That file has no header row")
    rows = count_rows(data, file_format)
    if rows > settings.max_import_rows:
        raise ValidationFailedError(
            f"That file has {rows} rows; the limit is {settings.max_import_rows}"
        )

    job = ImportJob(
        owner_user_id=user.id,
        file_name=file_name,
        storage_key="",
        file_format=file_format,
        mapping_config={},
        status="pending",
        total_rows=rows,
    )
    session.add(job)
    await session.flush()
    await session.refresh(job)

    key = importer.import_storage_key(user.id, job.id, file_format)
    get_storage(settings).save(key, data)
    job.storage_key = key

    await record_audit(
        session,
        action="import.create",
        owner_user_id=user.id,
        entity_type="import_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={"file_name": file_name, "format": file_format, "rows": rows},
    )
    return _import_out(
        job,
        columns=header,
        suggested=importer.suggest_mapping(header),
    )


@imports_router.get("/{job_id}", response_model=ImportJobOut)
async def import_detail(
    job_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ImportJobOut:
    job = await importer.get_import_job(session, user.id, job_id)
    return _import_out(job)


@imports_router.post("/{job_id}/run", response_model=ImportJobOut, dependencies=[Csrf])
async def run_import(
    request: Request,
    job_id: uuid.UUID,
    payload: ImportRunIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> ImportJobOut:
    """Run the import with the mapping the operator confirmed."""
    job = await importer.get_import_job(session, user.id, job_id)
    if job.status not in {"pending", "failed"}:
        raise ValidationFailedError(
            f"This import is '{job.status}' and cannot be started again",
            details={"status": job.status},
        )
    if payload.duplicate_strategy not in importer.DUPLICATE_STRATEGIES:
        raise ValidationFailedError(
            f"Unknown duplicate strategy '{payload.duplicate_strategy}'",
            details={"available": list(importer.DUPLICATE_STRATEGIES)},
        )
    # Checked against the file before the job is queued: a mapping that cannot
    # import anything is refused now, not after the operator has been told the
    # import started.
    mapping = importer.validate_mapping_for_job(job, payload.mapping, settings=settings)

    job.mapping_config = {
        "columns": mapping,
        "duplicate_strategy": payload.duplicate_strategy,
    }
    job.status = "queued"
    job.error_details = None
    await record_audit(
        session,
        action="import.run",
        owner_user_id=user.id,
        entity_type="import_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={
            "mapped_fields": sorted(set(payload.mapping.values())),
            "duplicate_strategy": payload.duplicate_strategy,
        },
    )
    mode = await importer.dispatch_import(session, job, background_tasks)
    logger.info("import_dispatched", job_id=str(job.id), mode=mode)
    return _import_out(job)


@imports_router.delete("/{job_id}", response_model=ImportJobOut, dependencies=[Csrf])
async def delete_import(
    request: Request,
    job_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> ImportJobOut:
    """Remove the uploaded file. The row keeps the history of what was imported."""
    job = await importer.get_import_job(session, user.id, job_id)
    importer.delete_import_file(job, settings=settings)
    await record_audit(
        session,
        action="import.delete",
        owner_user_id=user.id,
        entity_type="import_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={"file_name": job.file_name},
    )
    return _import_out(job)
