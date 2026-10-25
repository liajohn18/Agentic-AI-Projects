from schemas import AMLTransaction

def extract_transaction(raw_data: dict) -> AMLTransaction:
    return AMLTransaction.model_validate(raw_data)


raw_transaction = {
    "transaction_id": "TX-1001",
    "amount": "12500.50",
    "currency": "USD",
    "timestamp": "2026-10-22T09:30:00Z",
    "sender_name": "Northwind Trading",
    "beneficiary_name": "Cedar Imports",
    "channel": "wire",
    "description": "Monthly supplier payment",
}

transaction = extract_transaction(raw_transaction)
print(transaction)