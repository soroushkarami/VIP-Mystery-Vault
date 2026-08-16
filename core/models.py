from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Store(models.Model):
    name = models.CharField(max_length=200)
    markup_percent = models.PositiveIntegerField(default=80,
                                                 help_text='80 means 80% markup')
    subscription_active = models.BooleanField(default=True)
    subscription_expiry = models.DateTimeField(null=True,   # The db is allowed to leave this cell EMPTY
                                               blank=True)  # The website form is allowed to leave this field EMPTY
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)

    # Link this store to a Django User; ensures each user can own only one store.
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,      # Allows admin to create stores without a user (for testing)
        blank=True,
        related_name='store'    # This lets us do: request.user.store
    )

    is_demo = models.BooleanField(default=False)

    @property
    def days_remaining(self):
        """Return days remaining until subscription expiry, or None if no expiry date."""
        if not self.subscription_expiry:
            return None
        now = timezone.now()
        if self.subscription_expiry < now:
            return 0

        remained = self.subscription_expiry - now
        return remained.days

    @property
    def is_subscription_active(self):
        if not self.subscription_active:
            return False
        if self.subscription_expiry:
            return self.subscription_expiry > timezone.now()    # if expiration is later than now return True
        return True     # if no expiry is set -> active

    def __str__(self):
        return self.name


class ProductMain(models.Model):
    """Main info for a product family (shared across all sizes)"""
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='product_main')
    name = models.CharField(max_length=300)
    category = models.CharField(max_length=60)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    product_code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    color = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} [{self.product_code}]'

    class Meta:
        unique_together = ['store', 'product_code']  # Ensure product_code is unique per store


class Product(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='products')
    # Link to ProductMain
    main = models.ForeignKey(ProductMain, on_delete=models.CASCADE, related_name='variants',
                             null=True, blank=True)

    # Size-specific fields
    sku = models.CharField(max_length=50, unique=True)
    size = models.CharField(max_length=20,
                            choices=[('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL'),
                                     ('XXL', 'XXL'), ('XXXL', 'XXXL')])
    # ('XL','XL'):
    # First 'XL' = The value saved in the database (referred to as db_value).
    # Second 'XL' = The value displayed in dropdown menus (referred to as display_value).
    price = models.DecimalField(max_digits=15, decimal_places=0)    # Tomans --> no decimals
    stock = models.PositiveIntegerField(default=0)
    is_out_of_stock = models.BooleanField(default=False)

    def __str__(self):
        if self.main:
            return f'{self.main.name} [{self.sku}]'
        return f'Product {self.sku} (no main)'

    @property
    def name(self):
        return self.main.name

    @property
    def category(self):
        return self.main.category

    @property
    def image(self):
        return self.main.image

    @property
    def color(self):
        return self.main.color

    @property
    def product_code(self):
        return self.main.product_code

    @property
    def has_image(self):
        return bool(self.main.image)


class Customer(models.Model):
    store = models.ForeignKey(Store,
                              on_delete=models.CASCADE,
                              related_name='customers')
    phone = models.CharField(max_length=15, unique=True)
    size = models.CharField(max_length=20,
                            choices=[('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL'),
                                     ('XXL', 'XXL'), ('XXXL', 'XXXL')])

    # Style tags as JSON: e.g., {"categories": {"Jacket": 3, "Shirt": 1}}
    style_tags = models.JSONField(default=dict)
    visit_count = models.PositiveIntegerField(default=0)
    last_visit = models.DateTimeField(null=True, blank=True)
    last_deal_generated = models.DateTimeField(null=True, blank=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    notification_message = models.TextField(blank=True, null=True)
    special_offer_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # fingerprint + IP for phone verification
    fingerprint = models.CharField(max_length=255, null=True, blank=True,
                                   db_index=True)
    registration_ip = models.GenericIPAddressField(null=True, blank=True)
    shadow_banned = models.BooleanField(default=False)
    # user agreement
    consent_given = models.BooleanField(default=True)
    consent_given_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.phone} - {self.store}'

    def add_purchase(self, product):
        """Update style_tags based on purchased product category"""
        tags = self.style_tags.get('categories', {})

        # Add 1 to the category of the product they just bought
        tags[product.category] = tags.get(product.category, 0) + 1

        self.style_tags['categories'] = tags
        self.save()


class DailyDeal(models.Model):
    customer = models.ForeignKey(Customer,
                                 on_delete=models.CASCADE)
    product = models.ForeignKey(Product,
                                on_delete=models.CASCADE)
    discount_percent = models.PositiveIntegerField()    # 10-30
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_claimed = models.BooleanField(default=False)     # if seller confirmed sold
    is_bought = models.BooleanField(default=False)    # if customer actually bought
    has_revealed = models.BooleanField(default=False)   # to make sure customer can only select 1 one of the deals
    auto_revealed = models.BooleanField(default=False)

    def __str__(self):
        return f'Deal for {self.customer.phone} - {self.product.name} : {self.discount_percent}%'

    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def create_deal(cls, customer, product, discount, hours=2):
        expiration = timezone.now() + timezone.timedelta(hours=hours)
        return cls.objects.create(
            customer=customer,
            product=product,
            discount_percent=discount,
            expires_at=expiration
        )


class Receipt(models.Model):
    store = models.ForeignKey(Store,
                              on_delete=models.CASCADE,
                              related_name='receipts')
    receipt_number = models.CharField(max_length=30, unique=True)
    amount = models.PositiveIntegerField()
    payment_method = models.CharField(max_length=50, choices=[
        ('cash', 'پول نقد'),
        ('bank', 'انتقال بانکی'),
        ('card', 'کارت به کارت'),
        ('online', 'پرداخت آنلاین')
    ], default='card')
    subscription_start = models.DateTimeField()
    subscription_end = models.DateTimeField()
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey('auth.User',
                                  on_delete=models.SET_NULL,
                                  null=True)
    is_paid = models.BooleanField(default=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f'{self.receipt_number} - {self.store.name}'

    @classmethod
    def generate_receipt_number(cls):
        year = timezone.now().year
        last_receipt = cls.objects.filter(
            issued_at__year=year
        ).order_by('-issued_at').first()

        if last_receipt:
            # Extract the number
            parts = last_receipt.receipt_number.split('-')
            if len(parts) == 3:
                try:
                    num = int(parts[2]) + 1
                except:
                    num = 1
            else:
                num = 1
        else:
            num = 1
        return f'INV-{year}-{str(num).zfill(3)}'