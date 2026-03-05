"""
Store SMTP credentials in the system credential vault (Windows Credential
Manager / macOS Keychain / Linux SecretService).

Run once:
    python store_credentials.py

The password is then read automatically by the app — no .env needed.
"""
import getpass
import keyring

SERVICE = "food-chaser"
USER    = "smtp"

print("Food Chaser — store SMTP credentials")
print("--------------------------------------")
print(f"Service : {SERVICE}")
print(f"Account : {USER}")
print()

existing = keyring.get_password(SERVICE, USER)
if existing:
    overwrite = input("A password is already stored. Overwrite? [y/N] ").strip().lower()
    if overwrite != "y":
        print("Aborted.")
        raise SystemExit(0)

password = getpass.getpass("Gmail App Password: ")
keyring.set_password(SERVICE, USER, password)
print("Password saved to credential vault.")
