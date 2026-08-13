import random
from django.utils import timezone
from django.shortcuts import render, redirect
from .models import DailyDeal, Product, Store
from PIL import Image
from io import BytesIO


def get_top_deals(customer, store, top_k=3):
    """
    The 'Brain' – picks the Top k products for a customer.
    Prioritizes: In Stock | Has Photo | Style Match | High Margin.
    Returns a list of DailyDeal objects.
    """
    # TODO 1. Base filter: size matches, in stock, not marked out of stock
    products = Product.objects.filter(
        store=store,
        size=customer.size,
        stock__gt=0,
        is_out_of_stock=False
    )

    # if no products matches customer's size, fall back to any size
    if not products.exists():
        products = Product.objects.filter(
            store=store,
            stock__gt=0,
            is_out_of_stock=False
        )

    # TODO 2. Score each product
    scores = []
    style_tags = {}

    # If customer CONSENTED, use style tags (personalized)
    if customer.consent_given:
        style_tags = customer.style_tags.get('categories', {})

        # If NO consent -> use empty style tags (random deals)

    for product in products:
        the_score = 0

        # BONUS: matching customer's style tags (more purchases = higher the_score)
        if product.category in style_tags:
            the_score += style_tags[product.category] * 5

        # BONUS: having photo
        if product.has_image:
            the_score += 10

        # BONUS: profit (higher price --> higher margin)
        the_score += int(product.price / 100000)    # 1 point for each 100,000 Toman

        scores.append((product, the_score))

    # TODO 3. Sort by score (highest first) and pick Top k
    scores.sort(key=lambda x: x[1], reverse=True)
    top_products = [p for p, s in scores[:top_k]]

    # TODO 4. Create DailyDeal objects
    deals = []
    for product in top_products:
        discount = calculate_safe_discount(product, store)
        deal = DailyDeal.create_deal(
            customer=customer,
            product=product,
            discount=discount,
            hours=2     # expiration
        )
        deals.append(deal)

    return deals


def calculate_safe_discount(product, store):
    """
    Calculate a safe discount percentage (10-30%) based on store markup.
    Higher markup = higher possible discount.
    """
    markup = store.markup_percent

    # Base discount: always at least 10%
    base_discount = 10

    # MAX discount depends on markup
    if markup >= 150:
        max_discount = 30       # High markup -> safe to discount more
    elif markup >= 100:
        max_discount = 25       # Medium-high markup -> moderate-high discount
    elif markup >= 80:
        max_discount = 20       # Medium markup -> moderate discount
    else:
        max_discount = 15       # Low markup -> discount carefully

    # base_discount < random discount < max_discount
    the_discount = random.randint(base_discount, max_discount)

    return the_discount


def is_in_cooldown(customer):
    if customer.cooldown_until and customer.cooldown_until > timezone.now():
        return True
    return False


def update_visit_and_cooldown(customer, made_purchase=False):
    """
    - If customer makes a purchase → Reset visit_count to 0 (reward them).
    - If customer visits 3 times without purchasing in 7 days → Cooldown.
    """
    # If they bought something, reset the counter (and clear cooldown)
    if made_purchase:
        customer.visit_count = 0
        customer.last_visit = timezone.now()
        customer.cooldown_until = None  # Remove cooldown if active
        customer.save()
        return False

    # normal visit tracking
    customer.visit_count += 1
    customer.last_visit = timezone.now()
    customer.save()

    # TODO: Trigger cooldown if 3 visits in 7 days without purchase
    seven_days_ago = timezone.now() - timezone.timedelta(days=7)

    if customer.visit_count >= 4 and customer.last_visit >= seven_days_ago:
        customer.cooldown_until = timezone.now() + timezone.timedelta(days=7)
        customer.visit_count = 0
        customer.save()
        return True

    return False


def get_special_offer(customer, store):
    """Generate the Final Offer: 1 absolute best match at 30% off"""
    products = Product.objects.filter(
        store=store,
        size=customer.size,
        stock__gt=0,
        is_out_of_stock=False
    )

    if not products.exists():
        return None

    # Score each product (same logic as get_top_deals, but with higher weights and picking only the best)
    style_tags = customer.style_tags.get('categories', {})
    scores = []

    for product in products:
        the_score = 0
        if product.category in style_tags:
            the_score += style_tags[product.category] * 10

        if product.has_image:
            the_score += 5

        the_score += int(product.price / 100000)

        scores.append((product, the_score))

    scores.sort(key=lambda x: x[1], reverse=True)
    best_product = scores[0][0]

    # Create a deal with 30% off (final offer)
    deal = DailyDeal.create_deal(
        customer=customer,
        product=best_product,
        discount=30,
        hours=8
    )

    return deal


def generate_sku(store_id, product_code, size, color=None):
    """
    Generate a unique SKU: STORE-PRODUCT_CODE-SIZE-COLOR
    Example: 1-DRESS-01-M-BLK
    """
    parts = [str(store_id), product_code, size]
    if color:
        parts.append(color)
    return '-'.join(parts)


def subscription_required(view_funcs):          # takes a view function as input.
    def wrapper(request, *args, **kwargs):      # the actual security guard; checks the user's
                                                # subscription before letting them through to the view.
        # 1. Check if user is logged in
        if not request.user.is_authenticated:
            return redirect('login')

        # 2. Check if their subscription is active
        try:
            store = request.user.store
            if not store.is_subscription_active:
                return render(request,
                              'core/subscription_expired.html',
                              {
                                  'store': store,
                                  'message': 'اشتراک شما منقضی شده است. لطفاً برای تمدید با پشتیبانی تماس بگیرید'
                              })
        except Store.DoesNotExist:
            pass

        # 3. If all checks pass (logged in, subscription active) → Let them in!
        return view_funcs(request, *args, **kwargs)
    return wrapper


def resize_image(image_file, max_size=800, quality=80):
    """
    Resize an image to max 800px width/height while maintaining aspect ratio.
    Returns the resized image as a BytesIO object ready for Django's ImageField.
    """
    # Open the image
    img = Image.open(image_file)
    # Check if image needs resizing
    width, height = img.size
    if width <= max_size and height <= max_size:
        # reset file pointer and return original
        image_file.seek(0)
        return image_file

    # Calculate new size (maintain aspect ratio)
    if width > height:
        new_width = max_size
        new_height = int(height * (max_size / width))
    else:
        new_height = max_size
        new_width = int(width * (max_size / height))

    # resize the img
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Save to BytesIO
    output = BytesIO()
    img.save(output,
             format='JPEG' if img.mode == 'RGB' else 'PNG',
             quality=quality,
             optimize=True)
    output.seek(0)

    return output
