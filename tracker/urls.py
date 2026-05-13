"""URL routes for the tracker app."""

from django.urls import path

from . import api_views, views

app_name = "tracker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("closeout/", views.closeout, name="closeout"),
    path("summary/", views.progress_summary, name="summary"),
    path("summary/<str:on_date>/", views.progress_summary, name="summary-on"),
    path("foods/", views.food_list, name="foods"),
    path("foods/add/", views.food_create, name="food-add"),
    path("foods/<int:food_id>/edit/", views.food_edit, name="food-edit"),
    path("recipes/", views.recipe_list, name="recipes"),
    path("recipes/add/", views.recipe_create, name="recipe-add"),
    path("recipes/<int:recipe_id>/edit/", views.recipe_edit, name="recipe-edit"),
    path("meals/", views.logged_meals, name="logged-meals"),
    path("htmx/meals/", views.log_meal, name="htmx-log-meal"),
    path("htmx/meals/undo/", views.undo_meal, name="htmx-undo-meal"),
    path("htmx/meals/template/", views.log_template, name="htmx-log-template"),
    path("htmx/meals/template/undo/", views.undo_template_log, name="htmx-undo-template-log"),
    path("htmx/foods/<int:food_id>/default/", views.food_default, name="htmx-food-default"),
    path("htmx/foods/search/", views.food_search, name="htmx-food-search"),
    path("htmx/habits/<str:field>/toggle/", views.toggle_habit, name="htmx-toggle-habit"),
    path("api/today/", api_views.today, name="api-today"),
    path("api/meals/", api_views.meals, name="api-meals"),
    path("api/daily/<str:log_date>/", api_views.daily_log, name="api-daily-log"),
    path("api/weight/", api_views.weight, name="api-weight"),
    path("api/summary/week/", api_views.week_summary, name="api-week-summary"),
    path("api/foods/", api_views.foods, name="api-foods"),
]
