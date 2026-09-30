from django.urls import path
from . import views

urlpatterns = [
    path('feed/', views.FeedView.as_view()),
    path('', views.PostListCreate.as_view()),
    path('<int:pk>/', views.PostDetail.as_view()),
    path('<int:post_id>/like/', views.toggle_like),
    path('<int:post_id>/bookmark/', views.toggle_bookmark),
    path('<int:post_id>/comments/', views.CommentListCreate.as_view()),
    path('<int:post_id>/repost/', views.repost),
    path('<int:post_id>/quote/', views.quote_post),
    path('<int:post_id>/pin/', views.pin_post),
    path('<int:post_id>/poll/', views.create_poll),
    path('<int:post_id>/analytics/', views.post_analytics),
    path('comments/<int:pk>/', views.delete_comment),
    path('comments/<int:comment_id>/like/', views.toggle_comment_like),
    path('polls/<int:poll_id>/vote/', views.vote_poll),
    path('bookmarks/', views.my_bookmarks),
    path('trending/', views.trending_hashtags),
    path('hashtag/<str:tag>/', views.by_hashtag),
    path('user/<str:username>/', views.user_posts),
    path('user/<str:username>/likes/', views.user_likes),
    path('user/<str:username>/media/', views.user_media),
    path('drafts/', views.drafts),
    path('scheduled/', views.schedule),
    path('searches/', views.saved_searches),
    path('searches/<int:pk>/', views.delete_saved_search),
]