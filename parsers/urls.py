from django.urls import path
from .views import SMSParseView, PDFParseView, RecategorizeMerchantView, PDFDebugView

urlpatterns = [
    path("sms/", SMSParseView.as_view(), name="sms-parse"),
    path("pdf/", PDFParseView.as_view(), name="pdf-parse"),
    path("pdf/debug/", PDFDebugView.as_view(), name="pdf-debug"),
    path("recategorize/", RecategorizeMerchantView.as_view(), name="recategorize"),
]
