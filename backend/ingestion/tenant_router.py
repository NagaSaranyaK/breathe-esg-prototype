"""
Tenant Router — Breathe ESG Mini-Ingest Portal

Per-tenant physical table isolation using raw DDL + dynamic Django model factory.
Each tenant gets three tables: tenant_{id}_ingestionlog, tenant_{id}_normalizedemissionrow,
and tenant_{id}_audittrail. Tables are created on first login and never touched by migrations.
"""

import threading
from django.db import connection

# ── Registry / caches ─────────────────────────────────────────────────────────

_table_registry: set = set()   # org_ids whose tables are confirmed to exist
_model_cache: dict   = {}      # {org_id: (TenantLog, TenantRow, TenantAudit)}
_model_lock          = threading.Lock()


# ── DDL templates ─────────────────────────────────────────────────────────────

def _log_ddl(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id            SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    source_type   VARCHAR(30) NOT NULL,
    file_name     VARCHAR(255) NOT NULL,
    uploaded_file VARCHAR(255),
    uploaded_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    row_count     INTEGER DEFAULT 0,
    status        VARCHAR(15) DEFAULT 'PROCESSING'
)
"""


def _row_ddl(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id                   SERIAL PRIMARY KEY,
    tenant_id            INTEGER NOT NULL,
    ingestion_log_id     INTEGER NOT NULL,
    source_type          VARCHAR(30) NOT NULL,
    scope                SMALLINT,
    description          TEXT,
    source_reference     VARCHAR(255),
    raw_source_data      JSONB NOT NULL DEFAULT '{{}}',
    normalized_data      JSONB NOT NULL DEFAULT '{{}}',
    activity_value       NUMERIC(20,6),
    activity_unit        VARCHAR(20),
    emission_factor      NUMERIC(20,8),
    emission_factor_unit VARCHAR(30),
    co2e_mt              NUMERIC(20,6),
    period_start         DATE,
    period_end           DATE,
    status               VARCHAR(15) DEFAULT 'PENDING',
    flag_reason          TEXT,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    locked_at            TIMESTAMP WITH TIME ZONE
)
"""


def _audit_ddl(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id               SERIAL PRIMARY KEY,
    tenant_id        INTEGER NOT NULL,
    emission_row_id  INTEGER NOT NULL,
    actor            VARCHAR(255),
    action           VARCHAR(30),
    previous_status  VARCHAR(15),
    new_status       VARCHAR(15),
    notes            TEXT,
    timestamp        TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)
"""


# ── Table creation ─────────────────────────────────────────────────────────────

def _tname(org_id: int, kind: str) -> str:
    """Return the physical table name for a given org and table kind."""
    return f"tenant_{org_id}_{kind}"


def ensure_tenant_tables(org_id: int) -> None:
    """
    Create the three per-tenant tables if they do not already exist.
    Idempotent — safe to call on every login.
    """
    if org_id in _table_registry:
        return

    log_table   = _tname(org_id, "ingestionlog")
    row_table   = _tname(org_id, "normalizedemissionrow")
    audit_table = _tname(org_id, "audittrail")

    with connection.cursor() as cur:
        cur.execute(_log_ddl(log_table))
        cur.execute(_row_ddl(row_table))
        cur.execute(_audit_ddl(audit_table))

    _table_registry.add(org_id)


# ── Dynamic model factory ─────────────────────────────────────────────────────

def get_tenant_models(org_id: int):
    """
    Return (TenantLog, TenantRow, TenantAudit) dynamic model classes for org_id.
    Models are created once and cached; subsequent calls return the cached classes.
    Thread-safe via double-checked locking.
    """
    if org_id in _model_cache:
        return _model_cache[org_id]

    with _model_lock:
        if org_id in _model_cache:
            return _model_cache[org_id]

        from django.db import models as dm
        from .models import SourceType, IngestionStatus, EmissionStatus, EmissionScope, AuditAction

        app_label = "ingestion"

        # ── TenantLog ────────────────────────────────────────────────────────
        TenantLog = type(
            f"TenantLog_{org_id}",
            (dm.Model,),
            {
                "__module__": __name__,
                "tenant_id": dm.IntegerField(),
                "source_type":     dm.CharField(max_length=30, choices=SourceType.choices),
                "file_name":       dm.CharField(max_length=255),
                "uploaded_file":   dm.FileField(upload_to="uploads/", null=True, blank=True),
                "uploaded_at":     dm.DateTimeField(auto_now_add=True),
                "row_count":       dm.IntegerField(default=0),
                "status":          dm.CharField(max_length=15, default=IngestionStatus.PROCESSING),
                # Expose Status/SourceType as class attrs for compatibility
                "Status":          IngestionStatus,
                "SourceType":      SourceType,
                "Meta": type("Meta", (), {
                    "db_table":  _tname(org_id, "ingestionlog"),
                    "managed":   False,
                    "app_label": app_label,
                }),
            },
        )

        # ── TenantRow ────────────────────────────────────────────────────────
        TenantRow = type(
            f"TenantRow_{org_id}",
            (dm.Model,),
            {
                "__module__": __name__,
                "tenant_id":  dm.IntegerField(),
                "ingestion_log_id": dm.IntegerField(),
                "source_type":  dm.CharField(max_length=30, choices=SourceType.choices),
                "scope":        dm.SmallIntegerField(null=True, blank=True, choices=EmissionScope.choices),
                "description":  dm.TextField(null=True, blank=True),
                "source_reference": dm.CharField(max_length=255, null=True, blank=True),
                "raw_source_data":  dm.JSONField(default=dict),
                "normalized_data":  dm.JSONField(default=dict),
                "activity_value":   dm.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True),
                "activity_unit":    dm.CharField(max_length=20, null=True, blank=True),
                "emission_factor":  dm.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True),
                "emission_factor_unit": dm.CharField(max_length=30, null=True, blank=True),
                "co2e_mt":      dm.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True),
                "period_start": dm.DateField(null=True, blank=True),
                "period_end":   dm.DateField(null=True, blank=True),
                "status":       dm.CharField(max_length=15, default=EmissionStatus.PENDING),
                "flag_reason":  dm.TextField(null=True, blank=True),
                "created_at":   dm.DateTimeField(auto_now_add=True),
                "locked_at":    dm.DateTimeField(null=True, blank=True),
                # Expose Status/SourceType/Scope as class attrs for compatibility
                "Status":    EmissionStatus,
                "SourceType": SourceType,
                "Scope":     EmissionScope,
                "Meta": type("Meta", (), {
                    "db_table":  _tname(org_id, "normalizedemissionrow"),
                    "managed":   False,
                    "app_label": app_label,
                }),
            },
        )

        # ── TenantAudit ──────────────────────────────────────────────────────
        TenantAudit = type(
            f"TenantAudit_{org_id}",
            (dm.Model,),
            {
                "__module__": __name__,
                "tenant_id": dm.IntegerField(),
                "emission_row_id": dm.IntegerField(),
                "actor":           dm.CharField(max_length=255, null=True, blank=True),
                "action":          dm.CharField(max_length=30, null=True, blank=True, choices=AuditAction.choices),
                "previous_status": dm.CharField(max_length=15, null=True, blank=True),
                "new_status":      dm.CharField(max_length=15, null=True, blank=True),
                "notes":           dm.TextField(null=True, blank=True),
                "timestamp":       dm.DateTimeField(auto_now_add=True),
                "Action":          AuditAction,
                "Meta": type("Meta", (), {
                    "db_table":  _tname(org_id, "audittrail"),
                    "managed":   False,
                    "app_label": app_label,
                }),
            },
        )

        _model_cache[org_id] = (TenantLog, TenantRow, TenantAudit)
        return _model_cache[org_id]


# ── Serializer factory ────────────────────────────────────────────────────────

def make_tenant_serializers(TenantLog, TenantRow, TenantAudit):
    """
    Return (LogSerializer, RowSerializer) DRF serializer classes
    bound to the supplied dynamic model classes.
    """
    from rest_framework import serializers

    class TenantAuditSerializer(serializers.ModelSerializer):
        class Meta:
            model  = TenantAudit
            fields = ["id", "actor", "action", "previous_status", "new_status", "notes", "timestamp"]

    class TenantLogSerializer(serializers.ModelSerializer):
        class Meta:
            model  = TenantLog
            fields = "__all__"

    class TenantRowSerializer(serializers.ModelSerializer):
        audit_trail = serializers.SerializerMethodField()

        def get_audit_trail(self, obj):
            entries = TenantAudit.objects.filter(
                emission_row_id=obj.pk
            ).order_by("timestamp")
            return TenantAuditSerializer(entries, many=True).data

        class Meta:
            model  = TenantRow
            fields = [
                "id", "tenant_id", "ingestion_log_id", "source_type", "scope",
                "description", "source_reference", "raw_source_data", "normalized_data",
                "activity_value", "activity_unit", "emission_factor", "emission_factor_unit",
                "co2e_mt", "period_start", "period_end", "status", "flag_reason",
                "created_at", "locked_at", "audit_trail",
            ]

    return TenantLogSerializer, TenantRowSerializer
