from django.urls import path
from . import views

urlpatterns = [
    path('follow/<int:user_id>/', views.toggle_follow),
    path('follow/accept/<int:req_id>/', views.accept_follow_request),
    path('follow/reject/<int:req_id>/', views.reject_follow_request),
    path('follow/requests/', views.pending_follow_requests),
    path('followers/<str:username>/', views.user_followers),
    path('following/<str:username>/', views.user_following),
    path('notifications/', views.notifications),
    path('notifications/read/', views.mark_read),
    path('notifications/read/<int:pk>/', views.mark_read),
    path('report/', views.create_report),
    path('react/<int:post_id>/', views.react_to_post),
    path('conversations/', views.conversations),
    path('conversations/<int:conv_id>/messages/', views.conversation_messages),
    path('conversations/<int:conv_id>/send/', views.send_message),
    path('conversations/<int:conv_id>/media/', views.upload_message_media),
    path('conversations/<int:conv_id>/typing/', views.typing),
    path('conversations/<int:conv_id>/typing/who/', views.who_is_typing),
]