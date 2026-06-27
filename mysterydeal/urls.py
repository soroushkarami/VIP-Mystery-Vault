from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('soroush_panel/', admin.site.urls),    # renamed admin/ --> soroush_panel/
    path('', include('core.urls')),
    path('', include('django.contrib.auth.urls')),   # Adds /login/, /logout/
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)