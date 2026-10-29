from django.urls import path

from . import views

app_name = 'prospectos'
urlpatterns = [
    path('cola/', views.cola, name='cola'),
    path('familias/', views.familias_por_unir, name='familias'),
    path('publicar/', views.publicar_google, name='publicar'),
    path('respuestas/', views.respuestas, name='respuestas'),
    path('respuestas/<int:pk>/', views.respuesta, name='respuesta'),
    path('ayuda/', views.ayuda, name='ayuda'),
    path('primeros-pasos/', views.pasos, name='pasos'),
    path('mapa/', views.mapa, name='mapa'),
    path('preparatorias/ubicar/', views.ubicar, name='ubicar'),
    path('mapa/configurar/', views.configurar_mapa, name='configurar_mapa'),
    path('otras-computadoras/', views.otras_computadoras, name='otras_computadoras'),
    path('reporte/', views.reporte, name='reporte'),
    path('scoring/', views.configuracion, name='configuracion'),
    path('evento/<int:pk>/en-vivo/', views.evento_vivo, name='evento_vivo'),
    path('evento/<int:pk>/en-vivo/datos/', views.evento_vivo_datos, name='evento_vivo_datos'),
    path('evento/<int:pk>/qr/', views.evento_qr, name='evento_qr'),
    path('evento/<int:pk>/solicitud/', views.evento_solicitud, name='evento_solicitud'),
    path('evento/<int:pk>/reporte/', views.evento_reporte, name='evento_reporte'),
    path('preparatoria/<int:pk>/qr/', views.prepa_qr, name='prepa_qr'),
    path('evento/<int:pk>/tarjetas/', views.tarjetas, name='tarjetas'),
    path('formulario/<int:pk>/mapeo/', views.mapeo, name='mapeo'),
]
