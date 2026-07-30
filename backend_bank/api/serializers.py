from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Account, Transaction

User = get_user_model()


class AccountSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Account
        fields = ["id", "account_number", "username", "balance", "created_at"]
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    sender_account_number = serializers.CharField(
        source="sender.account_number", read_only=True
    )
    receiver_account_number = serializers.CharField(
        source="receiver.account_number", read_only=True
    )

    class Meta:
        model = Transaction
        fields = [
            "id",
            "sender_account_number",
            "receiver_account_number",
            "amount",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class SendMoneySerializer(serializers.Serializer):
    """Input validation for POST /api/transactions/send/"""

    receiver_account_number = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)

    def validate_amount(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_receiver_account_number(self, value):
        if not Account.objects.filter(account_number=value).exists():
            raise serializers.ValidationError("No account with that account number.")
        return value