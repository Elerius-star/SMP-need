"""
accounts/signals.py
───────────────────
User creation triggers: settings row, trust score, welcome email,
audit log entry, activity cache, suggestion cache.
"""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def user_created(sender, instance, created, **kwargs):
    """Bootstrap all auxiliary rows when a User is created."""
    if not created:
        return

    # 1. Settings row
    try:
        from .models import UserSettings
        UserSettings.objects.get_or_create(user=instance)
    except Exception as e:
        logger.warning('UserSettings create failed: %s', e)

    # 2. Trust score
    try:
        from .models_extras import UserTrustScore
        UserTrustScore.objects.get_or_create(user=instance)
    except ImportError:
        pass

    # 3. Activity feed cache
    try:
        from .models_extras import ActivityFeedCache
        ActivityFeedCache.objects.get_or_create(user=instance)
    except ImportError:
        pass

    # 4. Audit log
    try:
        from .models_extras import AuditLog
        AuditLog.objects.create(
            user=instance, action='register',
            metadata={'username': instance.username, 'email': instance.email},
        )
    except ImportError:
        pass

    # 5. Welcome email
    try:
        send_welcome_email(instance)
    except Exception as e:
        logger.warning('welcome email failed: %s', e)


@receiver(post_delete, sender=settings.AUTH_USER_MODEL)
def user_deleted(sender, instance, **kwargs):
    try:
        from .models_extras import AuditLog
        AuditLog.objects.create(
            user=None, action='delete_account',
            metadata={'username': instance.username, 'id': instance.id},
        )
    except ImportError:
        pass


def send_welcome_email(user):
    """Send a welcome email (silently no-op if email backend disabled)."""
    from django.core.mail import send_mail
    try:
        send_mail(
            subject='Welcome to SMP-Need',
            message=(
                f"Hi {user.username},\n\n"
                "Welcome to SMP-Need. Complete your profile to get started:\n"
                " - Add a bio and avatar\n"
                " - Follow a few people\n"
                " - Publish your first post\n\n"
                "— The SMP-Need Team"
            ),
            from_email='noreply@smp-need.app',
            recipient_list=[user.email],
            fail_silently=True,
        )
        return True
    except Exception as e:
        logger.warning('send_welcome_email: %s', e)
        return False


def log_action(user, action, target_type='', target_id='', metadata=None,
               ip_address=None, user_agent=''):
    """Convenience helper so views can record audit events."""
    try:
        from .models_extras import AuditLog
        return AuditLog.objects.create(
            user=user, action=action,
            target_type=target_type, target_id=str(target_id) if target_id else '',
            metadata=metadata or {}, ip_address=ip_address,
            user_agent=(user_agent or '')[:500],
        )
    except ImportError:
        return None