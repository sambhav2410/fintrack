"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json, logging

logger = logging.getLogger(__name__)

def version(request):
    return JsonResponse({"version": "gemini-v6", "model": "gemini-2.5-flash-lite"})

@csrf_exempt
def debug_log(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            msg = data.get("message", "")
            print(f"[AndroidLog] {msg}")
            logger.info(f"[AndroidLog] {msg}")
        except Exception:
            pass
    return JsonResponse({"ok": True})

urlpatterns = [
    path("version/", version),
    path("debug/log/", debug_log),
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/transactions/", include("transactions.urls")),
    path("api/parsers/", include("parsers.urls")),
    path("api/analytics/", include("analytics.urls")),
    path("api/budgets/", include("budgets.urls")),
]
