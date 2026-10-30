from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView

from prospectos import views

urlpatterns = [
    path('marca/logo.png', views.logo),
    path('marca/hoja-membretada.jpg', views.hoja_membretada),
    path('marca/fondo', views.fondo),
    path('conectar/', views.conectar, name='conectar'),
    path('conectar/Prospectos-UDC.crt', views.certificado, name='certificado'),
    path('salud/', lambda r: HttpResponse('prospectos-ok:' + views.huella(), content_type='text/plain')),
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path('admin/herramientas/', include('prospectos.urls')),
    path('admin/', admin.site.urls),
]
