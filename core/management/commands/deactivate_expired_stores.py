from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Store


class Command(BaseCommand):
    help = 'Deactivate stores with expired subscriptions'
    """
    it's run automatically by cron job specification defined in liara.json every Every 12 hours
    so that expired stores are automatically forbidden from using the system after expired subscription
    """

    def handle(self, *args, **options):
        now = timezone.now()
        expired_stores = Store.objects.filter(
            subscription_active=True,
            subscription_expiry__lt=now
        )
        count = expired_stores.update(subscription_active=False)
        self.stdout.write(f'Deactivated {count} expired stores.')
