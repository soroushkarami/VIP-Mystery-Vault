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

    # Link this store to a Django User; ensures each user can own only one store.
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,      # Allows admin to create stores without a user (for testing)
        blank=True,
        related_name='store'    # This lets us do: request.user.store
    )

    def __str__(self):
        return self.name


class Product(models.Model):
    store = models.ForeignKey(Store,
                              on_delete=models.CASCADE,
                              related_name='products')
    # Stock Keeping Unit (SKU) --> the ID for each product
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=300)
    price = models.DecimalField(max_digits=15,
                                decimal_places=0)   # Tomans --> no decimals
    size = models.CharField(max_length=20,
                            choices=[('S','S'), ('M','M'), ('L','L'), ('XL','XL'),
                                    ('XXL','XXL'), ('XXXL','XXXL')])
                            # ('XL','XL'):
                            # First 'XL' = The value saved in the database (referred to as db_value).
                            # Second 'XL' = The value displayed in dropdown menus (referred to as display_value).
    category = models.CharField(max_length=60)      # eg shirt, pants etc
    stock = models.PositiveIntegerField(default=0)
    is_out_of_stock = models.BooleanField(default=False)
    image = models.ImageField(upload_to='products/',
                              null=True, blank=True)

    def __str__(self):
        return f'{self.name} [{self.sku}]'

    @property
    def has_image(self):
        return bool(self.image)


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
    # fingerprint + IP for phone verification
    fingerprint = models.CharField(max_length=255, null=True, blank=True,
                                   db_index=True)
    registration_ip = models.GenericIPAddressField(null=True, blank=True)

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
