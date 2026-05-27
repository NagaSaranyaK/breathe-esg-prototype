import io
import json
from django.utils import timezone
from django.db import connection
from django.db.models import Count, Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

from .models import SourceType, IngestionStatus, EmissionStatus, AuditAction
from .normalization import process_csv
from .tenant_router import ensure_tenant_tables, get_tenant_models, make_tenant_serializers


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tenant_id(request):
    raw = request.headers.get("X-Tenant-ID", "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _require_tenant(request):
    tenant_id = _get_tenant_id(request)
    if not tenant_id:
        return Response(
            {"error": "X-Tenant-ID header is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    TenantLog, TenantRow, TenantAudit = get_tenant_models(tenant_id)
    return tenant_id, TenantLog, TenantRow, TenantAudit


# ── Auth / Login ──────────────────────────────────────────────────────────────

class TenantLoginView(APIView):
    """
    POST /api/auth/login/
    Body: { tenant_id (int), username (str), password (str) }
    Credentials: username=test-{id}, password=pass-{id}
    """

    def post(self, request):
        tenant_id = request.data.get("tenant_id")
        username  = request.data.get("username", "")
        password  = request.data.get("password", "")

        try:
            tenant_id = int(tenant_id)
            if tenant_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "tenant_id must be a positive integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if username != f"test-{tenant_id}" or password != f"pass-{tenant_id}":
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        org_name = f"Tenant {tenant_id}"
        org_slug = f"tenant-{tenant_id}"
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_tenant (id, name, slug, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (id) DO NOTHING
                """,
                [tenant_id, org_name, org_slug],
            )
            cur.execute(
                "SELECT setval(pg_get_serial_sequence('ingestion_tenant','id'), "
                "GREATEST(nextval(pg_get_serial_sequence('ingestion_tenant','id')), %s))",
                [tenant_id + 1],
            )
            cur.execute("SELECT name FROM ingestion_tenant WHERE id = %s", [tenant_id])
            row = cur.fetchone()
            if row:
                org_name = row[0]

        ensure_tenant_tables(tenant_id)
        return Response({"tenant_id": tenant_id, "org_name": org_name})


# ── Ingestion Logs ────────────────────────────────────────────────────────────

class IngestionLogListView(APIView):
    """GET /api/ingestion-logs/ — upload history for the tenant."""

    def get(self, request):
        result = _require_tenant(request)
        if isinstance(result, Response):
            return result
        tenant_id, TenantLog, TenantRow, TenantAudit = result

        logs = TenantLog.objects.filter(tenant_id=tenant_id).order_by("-uploaded_at")
        LogSerializer, _ = make_tenant_serializers(TenantLog, TenantRow, TenantAudit)
        return Response(LogSerializer(logs, many=True).data)


# ── File Upload (base + three typed subclasses) ───────────────────────────────

class _UploadBaseView(APIView):
    """
    Shared upload logic for all three source types.

    POST body (multipart/form-data):
        file  — CSV file
    X-Tenant-ID header required.
    """
    parser_classes = [MultiPartParser, FormParser]
    source_type: str = None

    def post(self, request):
        result = _require_tenant(request)
        if isinstance(result, Response):
            return result
        tenant_id, TenantLog, TenantRow, TenantAudit = result

        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        if not file.name.lower().endswith(".csv"):
            return Response({"error": "Only .csv files are accepted"}, status=status.HTTP_400_BAD_REQUEST)

        mapping_payload = request.data.get("column_mapping", "")
        column_mapping = None
        if mapping_payload:
            try:
                column_mapping = json.loads(mapping_payload)
            except json.JSONDecodeError:
                return Response(
                    {"error": "column_mapping must be valid JSON"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        file_content = file.read()
        file.seek(0)

        log = TenantLog.objects.create(
            tenant_id=tenant_id,
            source_type=self.source_type,
            file_name=file.name,
            uploaded_file=file,
            status=IngestionStatus.PROCESSING,
        )

        try:
            summary = process_csv(
                io.BytesIO(file_content),
                self.source_type,
                log,
                TenantRow,
                column_mapping=column_mapping,
            )
            return Response(summary, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response(
                {"error": str(exc), "rows_created": 0, "flagged_rows": 0, "approved_rows": 0},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UploadSAPView(_UploadBaseView):
    """POST /api/upload/sap/"""
    source_type = SourceType.SAP_FUEL


class UploadUtilityView(_UploadBaseView):
    """POST /api/upload/utility/"""
    source_type = SourceType.UTILITY_ELECTRICITY


class UploadTravelView(_UploadBaseView):
    """POST /api/upload/travel/"""
    source_type = SourceType.CORPORATE_TRAVEL


# ── Emission Rows ─────────────────────────────────────────────────────────────

class EmissionRowListView(APIView):
    """
    GET /api/emissions/?status=

    status values:
        PENDING | FLAGGED | APPROVED | REJECTED
        NEEDS_REVIEW  →  returns PENDING + FLAGGED combined
    """

    def get(self, request):
        result = _require_tenant(request)
        if isinstance(result, Response):
            return result
        tenant_id, TenantLog, TenantRow, TenantAudit = result

        qs = TenantRow.objects.filter(tenant_id=tenant_id)

        status_param = request.query_params.get("status", "").upper()
        if status_param == "NEEDS_REVIEW":
            qs = qs.filter(
                status__in=[
                    EmissionStatus.PENDING,
                    EmissionStatus.FLAGGED,
                ]
            )
        elif status_param in ("PENDING", "FLAGGED", "APPROVED", "REJECTED"):
            qs = qs.filter(status=status_param)

        _, RowSerializer = make_tenant_serializers(TenantLog, TenantRow, TenantAudit)
        return Response(RowSerializer(qs, many=True).data)


# ── Row Actions ───────────────────────────────────────────────────────────────

class _RowActionBaseView(APIView):
    target_status: str = None
    audit_action: str  = None

    def post(self, request, pk):
        result = _require_tenant(request)
        if isinstance(result, Response):
            return result
        tenant_id, TenantLog, TenantRow, TenantAudit = result

        try:
            row = TenantRow.objects.get(pk=pk, tenant_id=tenant_id)
        except TenantRow.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if row.locked_at:
            return Response(
                {"error": f"Row is already {row.status.lower()} and cannot be modified. "
                          "Approved and rejected rows are immutable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous_status = row.status
        row.status    = self.target_status
        row.locked_at = timezone.now()
        row.save()

        TenantAudit.objects.create(
            tenant_id=tenant_id,
            emission_row_id=row.pk,
            actor="analyst@demo.com",
            action=self.audit_action,
            previous_status=previous_status,
            new_status=self.target_status,
        )

        _, RowSerializer = make_tenant_serializers(TenantLog, TenantRow, TenantAudit)
        return Response(RowSerializer(row).data)


class ApproveRowView(_RowActionBaseView):
    """POST /api/emissions/{id}/approve/"""
    target_status = EmissionStatus.APPROVED
    audit_action  = AuditAction.APPROVED


class RejectRowView(_RowActionBaseView):
    """POST /api/emissions/{id}/reject/"""
    target_status = EmissionStatus.REJECTED
    audit_action  = AuditAction.REJECTED


# ── Dashboard Summary ─────────────────────────────────────────────────────────

class DashboardSummaryView(APIView):
    """GET /api/dashboard/ — status counts, scope breakdown, total MTCO2e."""

    def get(self, request):
        result = _require_tenant(request)
        if isinstance(result, Response):
            return result
        tenant_id, TenantLog, TenantRow, TenantAudit = result

        qs = TenantRow.objects.filter(tenant_id=tenant_id)

        status_counts = {
            row["status"]: row["count"]
            for row in qs.values("status").annotate(count=Count("id"))
        }
        scope_counts = {
            row["scope"]: row["count"]
            for row in qs.values("scope").annotate(count=Count("id"))
        }
        total_co2e = (
            qs.filter(co2e_mt__isnull=False)
              .aggregate(total=Sum("co2e_mt"))["total"] or 0
        )

        pending  = status_counts.get("PENDING",  0)
        flagged  = status_counts.get("FLAGGED",  0)
        approved = status_counts.get("APPROVED", 0)
        rejected = status_counts.get("REJECTED", 0)

        return Response({
            "total_rows":    qs.count(),
            "pending":       pending,
            "flagged":       flagged,
            "approved":      approved,
            "rejected":      rejected,
            "needs_review":  pending + flagged,
            "scope_1":       scope_counts.get(1, 0),
            "scope_2":       scope_counts.get(2, 0),
            "scope_3":       scope_counts.get(3, 0),
            "total_co2e_mt": float(total_co2e),
        })

