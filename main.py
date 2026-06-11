print("Crypto X Agent démarré")

with open("accounts.txt", "r") as f:
    accounts = [line.strip() for line in f if line.strip()]

print("Comptes chargés :")
for account in accounts:
    print("-", account)
