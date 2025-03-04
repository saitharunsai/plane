# Python imports
from itertools import groupby
from datetime import timedelta

# Django import
from django.db import models
from django.db.models.functions import TruncDate
from django.db.models import Count, F, Sum, Value, Case, When, CharField
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear, Concat

# Module imports
from plane.db.models import Issue


def build_graph_plot(queryset, x_axis, y_axis, segment=None):

    temp_axis = x_axis

    if x_axis in ["created_at", "start_date", "target_date", "completed_at"]:
        year = ExtractYear(x_axis)
        month = ExtractMonth(x_axis)
        dimension = Concat(year, Value("-"), month, output_field=CharField())
        queryset = queryset.annotate(dimension=dimension)
        x_axis = "dimension"
    else:
        queryset = queryset.annotate(dimension=F(x_axis))
        x_axis = "dimension"

    if x_axis in ["created_at", "start_date", "target_date", "completed_at"]:
        queryset = queryset.exclude(x_axis__is_null=True)

    if segment in ["created_at", "start_date", "target_date", "completed_at"]:
        year = ExtractYear(segment)
        month = ExtractMonth(segment)
        dimension = Concat(year, Value("-"), month, output_field=CharField())
        queryset = queryset.annotate(segmented=dimension)
        segment = "segmented"

    queryset = queryset.values(x_axis)

    # Group queryset by x_axis field

    if y_axis == "issue_count":
        queryset = queryset.annotate(
            is_null=Case(
                When(dimension__isnull=True, then=Value("None")),
                default=Value("not_null"),
                output_field=models.CharField(max_length=8),
            ),
            dimension_ex=Coalesce("dimension", Value("null")),
        ).values("dimension")
        if segment:
            queryset = queryset.annotate(segment=F(segment)).values(
                "dimension", "segment"
            )
        else:
            queryset = queryset.values("dimension")

        queryset = queryset.annotate(count=Count("*")).order_by("dimension")

    if y_axis == "estimate":
        queryset = queryset.annotate(estimate=Sum("estimate_point")).order_by(x_axis)
        if segment:
            queryset = queryset.annotate(segment=F(segment)).values(
                "dimension", "segment", "estimate"
            )
        else:
            queryset = queryset.values("dimension", "estimate")

    result_values = list(queryset)
    grouped_data = {}
    for key, items in groupby(result_values, key=lambda x: x[str("dimension")]):
        grouped_data[str(key)] = list(items)

    sorted_data = grouped_data
    if temp_axis == "priority":
        order = ["low", "medium", "high", "urgent", "None"]
        sorted_data = {key: grouped_data[key] for key in order if key in grouped_data}
    else:
        sorted_data = dict(sorted(grouped_data.items(), key=lambda x: (x[0] == "None", x[0])))
    return sorted_data


def burndown_plot(queryset, slug, project_id, cycle_id):
    # Get all dates between the two dates
    date_range = [
        queryset.start_date + timedelta(days=x)
        for x in range((queryset.end_date - queryset.start_date).days + 1)
    ]

    chart_data = {str(date): 0 for date in date_range}

    # Total Issues in Cycle
    total_issues = queryset.total_issues

    completed_issues_distribution = (
        Issue.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            issue_cycle__cycle_id=cycle_id,
        )
        .annotate(date=TruncDate("completed_at"))
        .values("date")
        .annotate(total_completed=Count("id"))
        .values("date", "total_completed")
        .order_by("date")
    )

    for date in date_range:
        cumulative_pending_issues = total_issues
        total_completed = 0
        total_completed = sum(
            [
                item["total_completed"]
                for item in completed_issues_distribution
                if item["date"] is not None and item["date"] <= date
            ]
        )
        cumulative_pending_issues -= total_completed
        chart_data[str(date)] = cumulative_pending_issues

    return chart_data