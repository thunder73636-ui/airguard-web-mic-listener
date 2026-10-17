from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/sessions/", views.create_session, name="create_session"),
    path("api/sessions/<str:session_id>/", views.session_detail, name="session_detail"),
    path("api/sessions/<str:session_id>/candidates/<str:side>/", views.candidates, name="candidates"),
]
