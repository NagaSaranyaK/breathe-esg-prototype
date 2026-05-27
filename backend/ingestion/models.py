from django.db import models


# ── Standalone enum choices (no DB table) ─────────────────────────────────────

class SourceType(models.TextChoices):
    SAP_FUEL            = 'SAP_FUEL',            'SAP Fuel & Procurement'
    UTILITY_ELECTRICITY = 'UTILITY_ELECTRICITY',  'Utility Electricity'
    CORPORATE_TRAVEL    = 'CORPORATE_TRAVEL',      'Corporate Travel'


class IngestionStatus(models.TextChoices):
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETE   = 'COMPLETE',   'Complete'
    FAILED     = 'FAILED',     'Failed'


class EmissionStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending'
    FLAGGED  = 'FLAGGED',  'Flagged'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class EmissionScope(models.IntegerChoices):
    SCOPE_1 = 1, 'Scope 1 — Direct'
    SCOPE_2 = 2, 'Scope 2 — Purchased Energy'
    SCOPE_3 = 3, 'Scope 3 — Value Chain'


class AuditAction(models.TextChoices):
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    FLAGGED  = 'FLAGGED',  'Flagged'


# ── Static registry table ─────────────────────────────────────────────────────

class Tenant(models.Model):
    """
    A client company using the platform. All data is isolated by Tenant.
    This is the multi-tenancy boundary — no queryset should ever cross this key.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, help_text="URL-safe identifier, e.g. 'acme-corp'")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


# IngestionLog, NormalizedEmissionRow, AuditTrail static models were removed.
# All per-tenant data lives in dynamic tables (tenant_{id}_*).
# See ingestion/tenant_router.py.

