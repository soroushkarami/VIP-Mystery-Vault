from django.contrib import admin, messages
from .models import Store, Product, Customer, DailyDeal, Receipt
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'markup_percent', 'user', 'subscription_active',
                    'is_demo', 'receipt_link')
    list_filter = ('subscription_active', 'is_demo')
    search_fields = ('name', 'user__username')

    # custom button for generation
    readonly_fields = ('generate_receipt_button',)
    fieldsets = (
        (None, {
            'fields': ('name', 'markup_percent', 'user', 'logo',
                       'subscription_active', 'subscription_expiry',
                       'is_demo', 'generate_receipt_button')  # <-- add here
        }),
    )

    def generate_receipt_button(self, obj):
        if not obj or not obj.id:
            return "⚠️ Save the store first to generate a receipt."
        url = reverse('admin:generate_receipt', args=[obj.id])
        return format_html(
            '<a class="button" href="{}" style="background: #28a745; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-weight: bold;">🧾 Generate Receipt</a>',
            url
        )
    generate_receipt_button.short_description = ''

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:store_id>/generate-receipt/', self.admin_site.admin_view(self.generate_receipt),
                 name='generate_receipt'),
            path('receipt/<int:receipt_id>/view/', self.admin_site.admin_view(self.view_receipt), name='view_receipt'),
        ]
        return custom_urls + urls

    def generate_receipt(self, request, store_id):
        store = Store.objects.get(id=store_id)

        if request.method == 'POST':
            amount = request.POST.get('amount')
            payment_method = request.POST.get('payment_method')
            subscription_days = request.POST.get('subscription_days')

            # Create receipt
            receipt = Receipt.objects.create(
                store=store,
                receipt_number=Receipt.generate_receipt_number(),
                amount=amount,
                payment_method=payment_method,
                subscription_start=timezone.now(),
                subscription_end=timezone.now() + timezone.timedelta(days=int(subscription_days)),
                issued_by=request.user,
            )

            # Update store subscription
            store.subscription_active = True
            store.subscription_expiry = receipt.subscription_end
            store.save()

            messages.success(request, f'✅ Receipt {receipt.receipt_number} generated!')
            return redirect('admin:core_store_change', store_id)

        return render(request, 'admin/generate_receipt.html', {
            'store': store,
        })

    def view_receipt(self, request, receipt_id):
        receipt = Receipt.objects.get(id=receipt_id)
        return render(request, 'admin/view_receipt.html', {
            'receipt': receipt,
        })

    def receipt_link(self, obj):
        if obj.receipts.exists():
            last_receipt = obj.receipts.first()
            url = reverse('admin:view_receipt', args=[last_receipt.id])
            return format_html(
                '<a href="/soroush_panel/core/receipt/{}/view/">🧾 View Last</a>',
                last_receipt.id
            )
        return 'No receipt'

    receipt_link.short_description = 'Receipt'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'size', 'price', 'stock', 'is_out_of_stock', 'store', 'main')
    list_filter = ('store', 'size', 'main__category')
    search_fields = ('sku', 'main__name', 'main__product_code')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('phone', 'size', 'visit_count', 'store', 'consent_given')
    list_filter = ('store', 'phone', 'consent_given')

@admin.register(DailyDeal)
class DailyDealAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'discount_percent', 'expires_at', 'is_claimed')

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'store', 'amount', 'subscription_start', 'subscription_end', 'issued_at')
    list_filter = ('payment_method', 'is_paid')
    search_fields = ('receipt_number', 'store__name', 'store__user__username')

    # ── Make receipt_number read‑only ──
    readonly_fields = ('receipt_number',)

    # ── Optional: Disable manual "Add Receipt" entirely ──
    #def has_add_permission(self, request):
    #    return False

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:receipt_id>/view/', self.admin_site.admin_view(self.view_receipt), name='view_receipt'),
        ]
        return custom_urls + urls

    def view_receipt(self, request, receipt_id):
        receipt = Receipt.objects.get(id=receipt_id)
        return render(request, 'admin/view_receipt.html', {'receipt': receipt})
