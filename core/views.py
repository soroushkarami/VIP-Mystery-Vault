from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import FormView
from django.contrib import messages
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Store, Product, Customer, DailyDeal
from .forms import (UploadInventoryForm, CustomerRegistrationForm,
                    UsernameChangeForm, StoreLogoForm)
from .normalizer import (normalize_columns, persian_to_english_numbers,
                         normalize_size)
from .utils import (get_top_deals,
                    is_in_cooldown,
                    update_visit_and_cooldown,
                    get_special_offer,
                    generate_sku,
                    subscription_required,
                    resize_image)

import os
import pandas as pd
import zipfile
import qrcode
import json


class UploadInventoryView(LoginRequiredMixin, FormView):    # Only logged-in users(registered sellers) can access
    template_name = 'core/upload_inventory.html'
    form_class = UploadInventoryForm
    success_url = reverse_lazy('dashboard_home')   # if upload is successful, Redirect to dashboard

    def get_form_kwargs(self):
        """
        Ensures that when the form is created, it knows who the logged‑in user is
        """
        kwargs = super().get_form_kwargs()  # get Form's default args from FormView
        kwargs['user'] = self.request.user  # add the logged-in user to the form
        return kwargs   # pass the updated args to the FormView

    def form_valid(self, form):
        """
        runs automatically when Django determines the form is 100% valid (file types are correct, no viruses, etc.)
        """
        store = form.cleaned_data['store']      # cleaned_data: tool in FormView that checks if the file is a valid file
        excel_file = form.cleaned_data['excel_file']
        zip_file = form.cleaned_data['zip_images']

        #TODO 1. PROCESS EXCEL
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            messages.error(self.request,
                           f"Failed to read Excel: {str(e)}")
            return super().form_invalid(form)   # re-renders the page with the error message

        # Normalize Persian column names to English
        df = normalize_columns(df)

        products_created = 0
        errors = []
        sku_list = []

        # check columns: Name, Price, Size, Category, Stock, Color, ProductCode(-> Sku)
        for idx, row in df.iterrows():
            # NAME col
            name = row.get('Name', '-')

            # CATEGORY col
            category = row.get('Category', 'General')

            # PRICE col
            # Convert Persian numbers to English
            price_str = persian_to_english_numbers(row.get('Price', '0'))
            try:
                price = int(price_str) if price_str else 0
            except ValueError:
                errors.append(f"Invalid price for row {idx+2}: '{price_str}'")
                price = 0

            # STOCK col
            # Convert Persian numbers to English
            stock_str = persian_to_english_numbers(row.get('Stock', '0'))
            try:
                stock = int(stock_str) if stock_str else 0
            except ValueError:
                errors.append(f"Invalid stock for row '{idx+2}': '{stock_str}'")
                stock = 0

            # SIZE col
            # Normalize Persian sizes
            size = normalize_size(row.get('Size', 'M'))

            # COLOR col
            color = str(row.get('Color', '')).strip()

            # SKU col
            sku_found = False
            sku_from_excel = str(row.get('sku') or row.get('SKU') or row.get('Sku') or '').strip()
            if sku_from_excel:
                existing_product = Product.objects.filter(
                    store=store,
                    sku=sku_from_excel
                ).first()
                if existing_product:    # SKU exists in DB – use that instead of using Pruduct_code
                    sku_found = True
                    sku = sku_from_excel
                    product_code = existing_product.product_code or sku_from_excel
                    errors.append(f"Found existing product with SKU '{sku_from_excel}'. Will update.")
            if not sku_found:
                # Get product_code (for sku generation)
                product_code = str(row.get('ProductCode') or row.get('product_code') or row.get('Product_code') or '').strip()
                if not product_code:
                    # Auto-generate it from name
                    product_code = name.replace(' ', '-').upper()
                    # Limit length to avoid issues
                    product_code = product_code[:30]
                    # Add a warning so you know it was auto-generated
                    errors.append(f"ProductCode auto-generated for '{name}': {product_code}")
                # AUTO-GENERATE SKU col
                sku = generate_sku(store.id, product_code, size, color)
                if sku_from_excel and not sku_found:
                    errors.append(f"SKU '{sku_from_excel}' from Excel not found in DB. Generated new SKU: '{sku}'")

            # Update or create the product
            products, created = Product.objects.update_or_create(   # 'created' is boolean
                store =store,
                sku=sku,
                defaults={
                    'name':name,
                    'price':price,
                    'size':size,
                    'category':category,
                    'stock':stock,
                    'product_code': product_code,
                    'color': color,
                    'is_out_of_stock':False,
                }
            )
            products_created += 1 if created else 0
            sku_list.append(sku)

        # store the sku list in session for display
        self.request.session['uploaded_skus'] = sku_list
        self.request.session['store_id'] = store.id

        #TODO 2. PROCESS ZIP (if provided)
        if zip_file:
            try:
                with zipfile.ZipFile(zip_file, 'r') as zf:
                    for name in zf.namelist():
                        # Get the file extension (e.g., .jpg, .png)
                        base, ext = os.path.splitext(name)
                        sku_from_file = base.strip()
                        if not sku_from_file:
                            continue

                        # Check if it's an image file
                        if ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', 'webp']:
                            continue

                        # Find the product with this SKU
                        try:
                            # search for the product with that SKU in the store
                            product = Product.objects.get(store=store,
                                                          sku=sku_from_file)

                            # Read the file content and save it to the product's image field
                            file_content = zf.read(name)     # reads the raw bytes of the image
                            file_bytes = BytesIO(file_content)

                            # Resize and compress the image if needed
                            resized_img = resize_image(file_bytes, max_size=800, quality=80)

                            # Save the resized image to the product
                            product.image.save(f"{sku_from_file}{ext}",
                                               ContentFile(resized_img.read()),
                                               save=True)
                        except Product.DoesNotExist:
                            errors.append(f"SKU '{sku_from_file}' not found for image '{name}'")
                        except Exception as e:
                            errors.append(f"Error processing image '{name}': {str(e)}")

            except Exception as e:
                errors.append(f"ZIP processing error: {str(e)}")

        # TODO 3. SHOW RESULTS
        if errors:
            messages.warning(self.request,
                             f"Processed {products_created} products, but had issues: {', '.join(errors[:5])}")
        else:
            sku_message = "✅ Success! Products added/updated.\n\n📋 SKUs for your first 10 photos:\n"
            for sku in sku_list[:10]:  # Show first 10
                sku_message += f"  • {sku}.jpg\n"
            if len(sku_list) > 10:
                sku_message += f"  ... and {len(sku_list) - 10} more.\n"
            sku_message += "\n📸 Rename your photos to match these SKUs before uploading the ZIP."

            messages.success(self.request, sku_message)

        # calls the parent (FormView) which does the redirect to success_url (admin:index)
        return super().form_valid(form)


@login_required
def login_redirect(request):
    """Redirect admin users to admin panel, sellers to dashboard"""
    if request.user.is_superuser:
        return redirect('/soroush_panel/')
    else:
        return redirect('/dashboard/')


@login_required
def change_username(request):
    if request.method == 'POST':
        form = UsernameChangeForm(request.user, request.POST)
        if form.is_valid():
            new_username = form.cleaned_data['new_username']
            request.user.username = new_username
            request.user.save()
            messages.success(request,
                             'Username updated successfully!')
            return redirect('account_settings')
    else:
        form = UsernameChangeForm(request.user)

    return render(request,
                  'registration/username_change.html',
                  {'form': form})


@login_required
def account_settings(request):
    try:
        store = request.user.store
    except Store.DoesNotExist:
        store = None
    return render(request, 'registration/account.html', {'store': store})


@login_required
def upload_logo(request):
    try:
        store = request.user.store
    except Store.DoesNotExist:
        messages.error(request, 'No store linked to your acount.')
        return redirect('account_settings')

    if request.method == 'POST':
        form = StoreLogoForm(request.POST, request.FILES, instance=store)
        if form.is_valid():
            logo = request.FILES.get('logo')
            if logo:
                resized = resize_image(logo, max_size=400, quality=80)
                store.logo.save(logo.name,
                                ContentFile(resized.read()),
                                save=True)
                messages.success(request, 'Logo uploaded successfully!')
            return redirect('account_settings')

    else:
        form = StoreLogoForm(instance=store)

    return render(request,
                  'registration/upload_logo.html',
                  {
                      'form': form,
                      'store': store
                  })


# Seller Experience
# ---------- MAIN PAGE ----------
@subscription_required      # defined in utils
@login_required
def dashboard_home(request):
    try:
        store = request.user.store      # user.store → Returns the Store object linked to this user
    except Store.DoesNotExist:
        return render(request,
        'core/dashboard_home.html',
                {
            'error': 'No store linked to your account. Please contact support.',
            'store': None
        })

    # Count pending deals
    pending_deals = DailyDeal.objects.filter(
        customer__store=store,      # Only this store's customers
        is_claimed=False,
        expires_at__gt=timezone.now()   # gt: greater than; ie deals that are not expired yet
    ).count()

    # Count low stock products (stock between 1 and 3)
    low_stock = Product.objects.filter(
        store=store,
        stock__gt=0,    # exclude out of stock
        stock__lte=3
    ).count()

    # Count out of stock products
    out_of_stock = Product.objects.filter(
        store=store,
        is_out_of_stock=True
    ).count()

    # STATS:
    # get the start of this month (for stats)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # 1.customers this month
    total_customers = Customer.objects.filter(
        store=store,
        created_at__gte=month_start,
    ).count()
    # 2.sales this month
    total_sales = DailyDeal.objects.filter(
        customer__store=store,
        is_claimed=True,
        created_at__gte=month_start
    ).count()
    # 3.conversion rate
    if total_customers != 0:
        conversion = round(total_sales/total_customers * 100)
    else:
        conversion = 0

    return render(request,
                  'core/dashboard_home.html',
                  {
                      'store': store,
                      'pending_deals': pending_deals,
                      'low_stock_products': low_stock,
                      'out_of_stock_products': out_of_stock,
                      'days_remaining': store.days_remaining,
                      'total_customers': total_customers,
                      'total_sales': total_sales,
                      'conversion': conversion
                  })


# ---------- PENDING DEALS LIST ----------
@subscription_required
@login_required
def pending_deals(request):
    try:
        store = request.user.store
    except Store.DoesNotExist:
        return redirect('dashboard_home')

    deals = DailyDeal.objects.filter(
        customer__store=store,
        is_claimed=False,
        expires_at__gt=timezone.now()
    ).select_related('customer', 'product').order_by('-created_at')
    # Returns QuerySet of Deal objects
    # Passes the list of deals to the template

    # Calculate discounted price for each deal
    for deal in deals:
        deal.discounted_price = int(deal.product.price * (100 - deal.discount_percent) / 100)

    return render(request,
                  'core/pending_deals.html',
                  {
                      'store': store,
                      'deals': deals
                  })


# ---------- CONFIRM SOLD ----------
@subscription_required
@login_required
def confirm_sold(request, deal_id):
    if request.method != 'POST':
        return redirect('pending_deals')

    deal = get_object_or_404(DailyDeal, id=deal_id, is_claimed=False)

    # safety check – ensure the deal belongs to this user's store
    if deal.customer.store != request.user.store:
        messages.error(request, "You don't have permission to confirm this deal.")
        return redirect('pending_deals')

    # TODO 1. Subtract stock
    product = deal.product
    if product.stock > 0:
        product.stock -= 1
        if product.stock == 0:
            product.is_out_of_stock = True
        product.save()

    # TODO 2. Mark ONLY THIS DEAL as claimed
    deal.is_claimed = True
    deal.is_bought = True
    deal.save()

    # TODO 3. Delete the OTHER pending deals for this customer
    customer = deal.customer
    other_deals = DailyDeal.objects.filter(
        customer=customer,
        is_claimed=False,
        expires_at__gt=timezone.now()
    ).exclude(id=deal.id)

    count = other_deals.count()
    other_deals.delete()

    # TODO 4. Update customer style_tags (only for the purchased product)
    customer.add_purchase(product)

    # Reset visit count after purchase
    update_visit_and_cooldown(customer, made_purchase=True)

    messages.success(request,
                     f'✅ Deal confirmed! {product.name} sold to {customer.phone}. '
                     f'({count} deals removed)')
    return redirect('pending_deals')


# ---------- TOGGLE OUT OF STOCK ----------
@subscription_required
@login_required
def toggle_out_of_stock(request, product_id):
    if request.method != 'POST':
        return redirect('pending_deals')

    product = get_object_or_404(Product,
                                id=product_id)

    # Ensure this product belongs to the user's store
    if product.store != request.user.store:
        messages.error(request,
                       "You don't have permission to modify this product.")
        return redirect('pending_deals')

    product.is_out_of_stock = not product.is_out_of_stock
    # FLIP switch: If the product is currently "In Stock", it becomes "Out of Stock". If it is "Out of Stock", it becomes "In Stock".
    product.save()

    # TODO: If product is marked OUT OF STOCK, replace pending deals
    if product.is_out_of_stock:
        # Find all pending deals for this product
        pending_deals = DailyDeal.objects.filter(
            product=product,
            is_claimed=False,
            expires_at__gt=timezone.now()
        )

        for deal in pending_deals:
            customer = deal.customer
            store = product.store

            # mark the old deal as claimed so that it removes from dashboard
            deal.is_claimed = True
            deal.save()

            # Find a replacement product (same size, not out of stock)
            replacement = Product.objects.filter(
                store=store,
                size=product.size,
                stock__gt=0,
                is_out_of_stock=False
            ).exclude(id=product.id).first()

            if replacement:
                # Increase the discount for replacement deals
                original_discount = deal.discount_percent
                bonus_discount = 5  # Add 5% extra for the inconvenience
                new_discount = min(original_discount + bonus_discount, 30)  # Cap at 30%

                new_deal = DailyDeal.create_deal(
                    customer=customer,
                    product=replacement,
                    discount=new_discount,  # ← Higher discount!
                    hours=2
                )

                # Mark the NEW deal as auto-revealed (but don't lock others)
                new_deal.has_revealed = True  # Show the discount
                new_deal.save()

                # Clear the OLD deal's has_revealed
                deal.has_revealed = False
                deal.save()

                customer.notification_message = (
                    f"🔄 متأسفیم، {product.name} تمام شد! "
                    f"به جای آن {replacement.name} با تخفیف {new_discount}% (به جای {original_discount}%) تقدیم شما! 🎉"
                )
                customer.save()
                messages.info(request,
                              f"🔄 Replaced deal for {customer.phone}: {product.name} → {replacement.name} with {new_discount}% discount (was {original_discount}%)")
            else:
                # No replacement found → notify seller
                messages.warning(request,
                                 f"No replacement product found for {product.name}. Customer {customer.phone} will not get a new deal.")

    status = 'Out of Stock' if product.is_out_of_stock else 'In Stock'
    messages.success(request,
                     f'{product.name} is now {status}')

    return redirect('pending_deals')


# ---------- PRODUCT LIST (for Out of Stock toggle) ----------
@subscription_required
@login_required
def product_list(request):
    try:
        store = request.user.store
    except Store.DoesNotExist:
        return redirect('dashboard_home')

    products = Product.objects.filter(store=store).order_by('name')

    return render(request,
                  'core/product_list.html',
                  {
                      'store': store,
                      'products': products
                  })


@subscription_required
@login_required
def update_product(request):
    """
    AJAX view to update product stock and price.
    Only the seller who owns the store can update products.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'},
                            status=400)

    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        new_stock = int(data.get('stock'))
        new_price = int(data.get('price'))

        # Get the product
        product = get_object_or_404(Product, id=product_id)

        # Security: Ensure the product belongs to the logged-in user's store
        if product.store != request.user.store:
            return JsonResponse({'success': False,
                                 'error': 'You do not have permission to update this product.'},
                                status=403)
        # TODO: update product
        product.stock = new_stock
        product.price = new_price

        # Auto-toggle out of stock if stock is 0
        if new_stock == 0:
            product.is_out_of_stock = True
        else:
            product.is_out_of_stock = False

        product.save()

        return JsonResponse({
            'success': True,
            'new_stock': product.stock,
            'new_price': product.price,
            'is_out_of_stock': product.is_out_of_stock
        })

    except Product.DoesNotExist:
        return JsonResponse({'success': False,
                             'error': 'Product not found.'},
                            status=404)
    except ValueError:
        return JsonResponse({'success': False,
                             'error': 'Invalid stock or price.'},
                             status=400)
    except Exception as e:
        return JsonResponse({'success': False,
                             'error': str(e)},
                            status=500)


@subscription_required
@login_required
def view_skus(request):
    """Show a list of all SKUs for the seller's store (for photo naming)"""
    try:
        store = request.user.store
    except Store.DoesNotExist:
        messages.error(request,
                       'No store linked to your account.')
        return redirect('dashboard_home')

    products = Product.objects.filter(store=store).order_by('product_code', 'size')

    # group by product_code
    grouped = {}
    for product in products:
        key = product.product_code or 'no-code'
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(product)

    return render(request,
                  'core/view_skus.html',
                  {
                      'store': store,
                      'grouped': grouped,
                      'total': products.count()
                  })


@subscription_required
@login_required
def generate_qr(request):
    """Generate a QR code for the seller's store"""
    try:
        store = request.user.store
    except Store.DoesNotExist:
        messages.error(request,
                       'No store linked to your account.')
        return redirect('dashboard_home')

    # Build the URL for this store's scan page
    url = request.build_absolute_uri(f'/scan/{store.id}/')

    # TODO: create the QR code
    qr = qrcode.QRCode(
        version=5,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=30,
        border=4
    )
    qr.add_data(url)
    qr.make(fit=True)

    # create image
    img = qr.make_image(fill_color='black', back_color='white')

    # save to bytes
    buffer = BytesIO()      # Creates an in-memory file (not saved to disk)
    img.save(buffer, format='PNG')
    buffer.seek(0)      # Rewinds to the start of the buffer so it can be read.

    # Return as downloadable file
    response = HttpResponse(buffer, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="qr-code-{store.name}.png"'

    return response


@subscription_required
@login_required
def sales_detail(request):
    try:
        store = request.user.store
    except Store.DoesNotExist:
        return redirect('dashboard_home')

    # Get the start of the current month
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Get all claimed deals (sales) for this store in the current month
    sales = DailyDeal.objects.filter(
        customer__store=store,
        is_claimed=True,
        created_at__gte=month_start
    ).select_related('customer', 'product').order_by('-created_at')

    # Calculate discounted price for each sale
    for sale in sales:
        sale.discounted_price = int(sale.product.price * (100 - sale.discount_percent) / 100)

    # Summary stats
    total_sales = sales.count()
    total_revenue = sum(s.discounted_price for s in sales)

    return render(request, 'core/sales_detail.html', {
        'store': store,
        'sales': sales,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'month_name': now.strftime('%B %Y'),
    })

# Customer Experience
# ---------- QR SCAN ----------
def scan_qr(request, store_id=None):
    """
    Customer scans QR code → This view handles the request.
    - New customer: Show registration form (phone + size).
    - Returning customer: Show their 3 deals.
    """
    try:
        store = Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        return render(request,
                      'core/error.html',
                      {'error': 'Store not found.'})

    # Demo store LOCK
    is_demo = store.is_demo if store else False  # allow demo access but add demo banner in deals html

    # check if customer is identified by his/her browser's session (cookie)
    customer = None
    customer_id = request.session.get('customer_id', None)

    if customer_id:
        try:  # now that his id exists in session, let's try getting his object from db
            customer = Customer.objects.get(id=customer_id, store=store)
        except Customer.DoesNotExist:
            # Invalid session (the customer is not in our VIP system) --> clear session
            request.session.pop('customer_id', None)

    # If no customer in session, new customer --> show registration
    if not customer:
        if request.method == 'POST':
            form = CustomerRegistrationForm(request.POST)

            if form.is_valid():  # is_valid calls clean_phone and clean_size funcs in the forms module
                phone = form.cleaned_data['phone']
                size = form.cleaned_data['size']
                consent = form.cleaned_data.get('consent', True)    # getting consent bool to save the exact time and data

                # Anti-Spam: Check fingerprint limits BEFORE creating customer
                fingerprint = request.POST.get('fingerprint', '')
                ip = request.META.get('REMOTE_ADDR', '')

                # 🛡️ PSYCHOLOGICAL TRAP: Shadow ban flag
                shadow_banned = False

                # Rate limit by fingerprint (device)
                if fingerprint:
                    recent_fingerprint_count = Customer.objects.filter(
                        fingerprint=fingerprint,
                        created_at__gte=timezone.now() - timezone.timedelta(days=1)
                    ).count()

                    # Max 3 registrations per device per day
                    if recent_fingerprint_count >= 3:
                        # 🚫 SILENT BAN: Mark as shadow banned, NO error message
                        shadow_banned = True

                        # Also mark ALL existing customers with this fingerprint as shadow banned
                        Customer.objects.filter(fingerprint=fingerprint).update(shadow_banned=True)

                    # Rate limit by IP address
                    if ip and not shadow_banned:
                        recent_ip_count = Customer.objects.filter(
                            registration_ip=ip,
                            created_at__gte=timezone.now() - timezone.timedelta(hours=1)
                        ).count()

                        # Max 4 registrations from same IP per hour
                        if recent_ip_count >= 4:
                            # 🚫 SILENT BAN: Mark as shadow banned, NO error message
                            shadow_banned = True

                            # Also mark ALL existing customers with this IP as shadow banned
                            Customer.objects.filter(registration_ip=ip).update(shadow_banned=True)

                # Create or Get customer
                # why checking db again by 'get'?
                # she might have visited before but cleared her browser cookies. By using her phone number,
                # we can recover her old account + show her deals based on her previous purchases!
                customer, created = Customer.objects.get_or_create(
                    phone=phone,
                    store=store,
                    defaults={
                        'size': size,
                        'fingerprint': fingerprint,  # Save the device fingerprint
                        'registration_ip': ip,  # Save the user's ip
                        'shadow_banned': shadow_banned,  # 🛡️ PSYCHOLOGICAL TRAP
                    }
                )

                # If the customer already exists, we SHOULDN'T overwrite their fingerprint/IP.
                # Only update if it's a newly created customer (or if they somehow don't have one).
                if created:
                    customer.fingerprint = fingerprint
                    customer.registration_ip = ip
                    customer.shadow_banned = shadow_banned
                    customer.save()

                # if customer exists but size is different --> update it
                if not created and customer.size != size:
                    customer.size = size

                if created or (customer and not customer.consent_given):
                    customer.consent_given = consent
                    customer.consent_given_at = timezone.now() if consent else None

                customer.save()

                # save customer id in session (so they're identified on their next visit)
                request.session['customer_id'] = customer.id



                # redirect to show the deals
                return redirect('scan_qr',
                                store_id=store_id)

        # GET request: show registration form
        else:
            form = CustomerRegistrationForm()

        return render(request,
                      'core/register.html',
                      {
                          'store': store,
                          'form': form,
                          'is_demo': is_demo
                      })

    # Check if customer has a notification message (from replacement deal, etc.)
    notification = None
    if customer.notification_message:
        notification = customer.notification_message
        customer.notification_message = None  # Clear after reading
        customer.save()

    # for DEMO: reset all restrictions
    if is_demo and customer:
        customer.cooldown_until = None
        customer.visit_count = 0
        customer.shadow_banned = False
        customer.special_offer_used = False
        customer.save()

    # 🛡️ PSYCHOLOGICAL TRAP: Check if customer is shadow banned
    if customer.shadow_banned:
        # Show fake deals page (no discounts, no reveal)
        return render(request, 'core/shadow_banned.html', {
            'customer': customer,
            'store': store,
        })

    # customer already exists --> CHECK COOLDOWN
    if is_in_cooldown(customer) and not is_demo:
        return render(request,
                      'core/cooldown.html',
                      {
                          'customer': customer,
                          'cooldown_until': customer.cooldown_until
                      })

    # UPDATE VISIT COUNT
    if not is_demo:
        cooldown_triggered = update_visit_and_cooldown(customer, made_purchase=False)
        if cooldown_triggered:
            return render(request,
                          'core/cooldown.html',
                          {
                              'customer': customer,
                              'cooldown_until': customer.cooldown_until,
                              'message': 'You have visited 3 times without purchasing. Take a week off, then come back for a special deal.!'
                          })
    else:
        customer.cooldown_until = None
        customer.save()

    # SPECIAL OFFER
    # Check if customer hasn't received the Special Offer yet (demo OR cooldown ended)
    if not is_demo:
        if (not customer.special_offer_used) and (customer.cooldown_until and customer.cooldown_until < timezone.now()):
            # Clear the cooldown flag
            customer.cooldown_until = None
            customer.save()

        # Generate Special Offer: 1 item at 30% off
        special_deal = get_special_offer(customer, store)
        if special_deal:
            customer.special_offer_used = True
            customer.save()
            return render(request, 'core/special_offer.html', {
                'customer': customer,
                'store': store,
                'deal': special_deal
            })

    # Check if customer already has ACTIVE pending deals before generating new deals
    existing_deals = DailyDeal.objects.filter(
        customer=customer,
        is_claimed=False,
        expires_at__gt=timezone.now()
    )

    if existing_deals.exists():
        # show existing deals since they're still valid
        deals = existing_deals
    else:
        # Check 24h limit (skip for DEMO)
        if not is_demo and customer.last_deal_generated and (
                customer.last_deal_generated > timezone.now() - timezone.timedelta(hours=24)):
            # Customer got deals in the last 24 hours --> Show waiting page
            next_available = customer.last_deal_generated + timezone.timedelta(hours=24)
            return render(request,
                          'core/wait.html',
                          {
                              'customer': customer,
                              'next_available': next_available,
                              'message': 'شما امروز تخفیف‌های خود را دریافت کرده‌اید.'
                          })

        # TODO: Generate deals (only if 24h limit is passed)
        deals = get_top_deals(customer, store, top_k=3)

        if not deals:
            return render(request,
                          'core/no_deals.html',
                          {
                              'customer': customer,
                              'store': store
                          })

        # Update last_deal_generated
        customer.last_deal_generated = timezone.now()
        customer.save()

    # Check if any deal for this customer has already been revealed (to keep it revealed even after refreshing)
    has_revealed = DailyDeal.objects.filter(
        customer=customer,
        is_claimed=False,
        has_revealed=True
    ).exists()

    revealed_deal = DailyDeal.objects.filter(
        customer=customer,
        is_claimed=False,
        has_revealed=True
    ).first()

    revealed_deal_id = revealed_deal.id if revealed_deal else None

    # ==== Check for auto-revealed replacement deal ====
    auto_revealed_id = None

    # If notification mentions replacement, find the auto-revealed deal
    if customer.notification_message and "تمام شد" in customer.notification_message:
        auto_revealed = DailyDeal.objects.filter(
            customer=customer,
            is_claimed=False,
            has_revealed=True
        ).first()
        if auto_revealed:
            auto_revealed_id = auto_revealed.id

    for deal in deals:      # we pass it directly to the HTML so that after refresh the discount is shown without using AJAX again
        deal.discounted_price = int(deal.product.price * (100 - deal.discount_percent) / 100)

    return render(request,
                  'core/deals.html',
                  {
                      'customer': customer,
                      'store': store,
                      'deals': deals,
                      'notification': notification,
                      'is_demo': is_demo,
                      'has_revealed': has_revealed,
                      'revealed_deal_id': revealed_deal_id,
                      'auto_revealed_id': auto_revealed_id
                  })


# ---------- FLIP THE CARD: REVEAL DISCOUNT (AJAX) ----------
def reveal_discount(request, deal_id):
    """
    Customer taps a card → Reveal the discount via AJAX.
    Returns JSON with discount percentage.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'invalid request'},
                            status=400)

    # check if customer is in session
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return JsonResponse({'error': 'Please scan the QR code again.'},
                            status=401)

    # The Database Lookup (Is this deal real?)
    try:
        deal = DailyDeal.objects.get(id=deal_id,
                                     customer_id=customer_id,
                                     is_claimed=False)
    except DailyDeal.DoesNotExist:
        return JsonResponse({'error': 'Deal not found or already claimed'},
                            status=404)

    # check if deal is expired
    if deal.is_expired():
        return JsonResponse({'error': 'Sorry, this deal is expired.'},
                            status=410)

    #  Check if any deal for this customer has already been revealed
    if DailyDeal.objects.filter(
        customer_id=customer_id,
        is_claimed=False,
        has_revealed=True
    ).exists():
        return JsonResponse({'error': 'You have already revealed a deal. You can only choose that one.'},
                            status=403)

    # Mark current deal as revealed
    deal.has_revealed = True
    deal.save()

    # return the discount
    discounted_price = deal.product.price * (100 - deal.discount_percent) / 100
    return JsonResponse({
        'discount_percent': deal.discount_percent,
        'product_name': deal.product.name,
        'product_price': str(deal.product.price),
        'discounted_price': str(int(discounted_price))
    })
    # This JSON package flies back to customer's phone.
    # The JavaScript catches it and updates the HTML to show "25% OFF!"


def update_consent(request, store_id):
    customer_id = request.session.get('customer_id')
    if customer_id:
        customer = get_object_or_404(Customer, id=customer_id)
        # toggle:
        customer.consent_given = not customer.consent_given
        customer.consent_given_at = timezone.now() if customer.consent_given else None
        customer.save()

        return redirect('scan_qr', store_id=store_id)


def demo_dashboard(request):
    """Static demo dashboard – shows how the seller panel works"""
    # get the demo store (id=3)
    demo_store = Store.objects.filter(is_demo=True).first()
    if not demo_store:
        return redirect('home')     # home is login page (core/urls)

    # Get the current customer from session (so that the deals are shown for each seller separately)
    customer_id = request.session.get('customer_id', None)
    customer = None
    if customer_id:
        try:
            customer = Customer.objects.get(id=customer_id, store=demo_store)
        except Customer.DoesNotExist:
            pass

    # Filter deals by this specific customer (if exists)
    demo_deals = DailyDeal.objects.filter(
        customer__store=demo_store,
        is_claimed=False,
        expires_at__gt=timezone.now()
    )

    # If we have a customer, only show their deals
    if customer:
        demo_deals = demo_deals.filter(customer=customer)
        pending_count = demo_deals.count()
    else:
        demo_deals = demo_deals.none()
        pending_count = 0

    demo_deals = demo_deals.select_related('customer', 'product')[:5]

    return render(request,
                  'demo/demo_dashboard.html',
                  {
                      'store': demo_store,
                      'deals': demo_deals,
                      'is_demo': True,
                      'pending_deals': pending_count,
                      'customer_phone': customer.phone if customer else None
                  })


def landing_page(request):
    demo_store = Store.objects.filter(is_demo=True).first()
    return render(request,
                  'demo/landing.html',
                  {'demo_store_id': demo_store.id if demo_store else None}
                  )


def why_mystery_deal(request):
    return render(request, 'demo/why_mystery_deal.html')