from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("auth/login/",           views.TenantLoginView.as_view(),       name="tenant-login"),

    # Upload history
    path("ingestion-logs/",       views.IngestionLogListView.as_view(),  name="ingestion-log-list"),

    # CSV upload endpoints (one per source type)
    path("upload/sap/",           views.UploadSAPView.as_view(),         name="upload-sap"),
    path("upload/utility/",       views.UploadUtilityView.as_view(),     name="upload-utility"),
    path("upload/travel/",        views.UploadTravelView.as_view(),      name="upload-travel"),

    # Emission row list (filterable by status / needs_review)
    path("emissions/",            views.EmissionRowListView.as_view(),   name="emission-list"),

    # Row actions
    path("emissions/<int:pk>/approve/", views.ApproveRowView.as_view(),  name="emission-approve"),
    path("emissions/<int:pk>/reject/",  views.RejectRowView.as_view(),   name="emission-reject"),

    # Dashboard summary stats
    path("dashboard/",            views.DashboardSummaryView.as_view(),  name="dashboard-summary"),
]
