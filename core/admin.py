from django.contrib import admin
from .models import Store, Product, Customer, DailyDeal

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'markup_percent', 'subscription_active')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'price', 'size', 'stock', 'is_out_of_stock', 'store')
    list_filter = ('store', 'size', 'category')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('phone', 'size', 'visit_count', 'store')
    list_filter = ('store', 'phone')

@admin.register(DailyDeal)
class DailyDealAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'discount_percent', 'expires_at', 'is_claimed')
