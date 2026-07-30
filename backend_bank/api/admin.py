from django.contrib import admin

from .models import Account, IdempotencyKey, Transaction


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("account_number", "user", "balance", "created_at")
    search_fields = ("account_number", "user__username")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "sender", "receiver", "amount", "status", "created_at")
    list_filter = ("status",)


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("key", "user", "status", "request_path", "created_at")
    list_filter = ("status",)
    search_fields = ("key",)