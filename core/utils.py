import random
from django.utils import timezone
from .models import DailyDeal, Product


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
        max_discount = 30
    elif markup >= 100:
        max_discount = 25
    elif markup >= 80:
        max_discount = 20
    else:
        max_discount = 15

    # base_discount < random discount < max_discount
    the_discount = random.randint(base_discount, max_discount)

    return the_discount


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
    style_tags = customer.style_tags.get('categories', {})

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

    if customer.visit_count >= 3 and customer.last_visit >= seven_days_ago:
        customer.cooldown_until = timezone.now() + timezone.timedelta(days=7)
        customer.visit_count = 0
        customer.save()
        return True

    return False