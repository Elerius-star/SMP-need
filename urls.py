from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view()),
    path('login/', views.login_view),
    path('token/refresh/', TokenRefreshView.as_view()),
    path('me/', views.me_view),
    path('me/update/', views.update_me_view),
    path('me/avatar/', views.upload_avatar),
    path('me/banner/', views.upload_banner),
    path('me/settings/', views.my_settings),
    path('me/deactivate/', views.deactivate_account),
    path('me/reactivate/', views.reactivate_account),
    path('me/login-history/', views.login_history),
    path('me/sessions/', views.device_sessions),
    path('me/sessions/<int:pk>/revoke/', views.revoke_session),
    path('me/verification/', views.request_verification),
    path('password/change/', views.change_password),
    path('password/reset/', views.password_reset_request),
    path('password/reset/confirm/', views.password_reset_confirm),
    path('email/verify/', views.verify_email),
    path('users/search/', views.search_users),
    path('users/<str:username>/', views.UserDetailView.as_view()),
    path('users/<int:user_id>/block/', views.toggle_block),
    path('users/<int:user_id>/mute/', views.toggle_mute),
    path('blocks/', views.blocked_list),
    path('muted-words/', views.muted_words),
    path('muted-words/<int:pk>/', views.delete_muted_word),
]