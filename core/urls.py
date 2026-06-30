from django.urls import path
from django.views.generic import RedirectView
from .views import (
    UploadInventoryView,
    dashboard_home,
    pending_deals,
    confirm_sold,
    toggle_out_of_stock,
    product_list,
    scan_qr,
    reveal_discount,
    login_redirect,
    generate_qr,
    update_product
)

urlpatterns = [
    # Redirect root to login page
    path('', RedirectView.as_view(url='/login/', permanent=False), name='home'),

    path('upload-inventory/', UploadInventoryView.as_view(), name='upload_inventory'),
    path('login-redirect/', login_redirect, name='login_redirect'),

    # Dashboard URLs
    path('dashboard/', dashboard_home, name='dashboard_home'),
    path('dashboard/deals/', pending_deals, name='pending_deals'),
    path('dashboard/deal/<int:deal_id>/confirm/', confirm_sold, name='confirm_sold'),
    path('dashboard/product/<int:product_id>/toggle/', toggle_out_of_stock, name='toggle_out_of_stock'),
    path('dashboard/products/', product_list, name='product_list'),
    path('dashboard/qr/', generate_qr, name='generate_qr'),
    path('dashboard/update_product/', update_product, name='update_product'),

    # Customer QR URLs
    path('scan/<int:store_id>/', scan_qr, name='scan_qr'),
    path('deals/<int:store_id>/', scan_qr, name='show_deals'),
    path('reveal/<int:deal_id>/', reveal_discount, name='reveal_discount'),
]