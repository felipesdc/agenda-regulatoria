from apps.reports.views import Dashboard, Summary, Groups, ReportOccurrences, Export, FavoriteView
from apps.customfields.views import FieldView, FormView, ReferenceUsers
from apps.commitments.calendar_views import CalendarView, CalendarPeople, SavedFilterView
from apps.commitments.recurrence_views import HolidayView, PreviewView, SeriesOccurrenceView
from apps.notifications.views import DeliveryView, EmailView, PolicyView, MonitorView, RunJobsView
from django.urls import include
from rest_framework.routers import DefaultRouter
from apps.commitments.views import (
    CatalogView,
    CategoryView,
    DefinitionView,
    AssignableUsers,
)
from apps.audit.views import AuditList

from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from apps.accounts import views

urlpatterns = [
    path("api/v1/dashboard/", Dashboard.as_view()),
    path("api/v1/reports/summary/", Summary.as_view()),
    path("api/v1/reports/groups/", Groups.as_view()),
    path("api/v1/reports/occurrences/", ReportOccurrences.as_view()),
    path("api/v1/reports/export/", Export.as_view()),
    path("admin/", admin.site.urls),
    path("health/", views.health),
    path("ready/", views.ready),
    path("api/v1/auth/csrf/", views.csrf),
    path("api/v1/auth/login/", views.sign_in),
    path("api/v1/auth/logout/", views.sign_out),
    path("api/v1/auth/me/", views.me),
    path("api/v1/units/", views.UnitList.as_view()),
    path("api/v1/users/", views.UserList.as_view()),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

router = DefaultRouter()
router.register("report-favorites", FavoriteView, basename="report-favorite")
router.register("custom-fields", FieldView)
router.register("form-versions", FormView)
router.register("notifications", DeliveryView, basename="notification")
router.register("notification-policies", PolicyView, basename="notification-policy")
router.register("calendar-favorites", SavedFilterView, basename="calendar-favorite")
router.register("entities", CatalogView)
router.register("categories", CategoryView)
router.register("definitions", DefinitionView, basename="definition")
router.register("holidays", HolidayView)
router.register("occurrences", SeriesOccurrenceView, basename="occurrence")
urlpatterns += [
    path("api/v1/custom-field-users/", ReferenceUsers.as_view()),
    path("api/v1/notification-email/", EmailView.as_view()),
    path("api/v1/notification-monitor/", MonitorView.as_view()),
    path("api/v1/notification-jobs/", RunJobsView.as_view()),
    path("api/v1/assignable-users/", AssignableUsers.as_view()),
    path("api/v1/audit/", AuditList.as_view()),
    path("api/v1/", include(router.urls)),
]

urlpatterns += [
    path("api/v1/recurrence/preview/", PreviewView.as_view()),
    path("api/v1/calendar/", CalendarView.as_view()),
    path("api/v1/calendar/people/", CalendarPeople.as_view()),
]
