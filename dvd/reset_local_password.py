"""
ISweep DVD - Local Development Password Reset

Resets the password for an existing local ISweep account without
deleting the account, preferences, filters, or other database data.

Development utility only.
"""

import sqlite3

from werkzeug.security import generate_password_hash

from dvd.password_input import masked_password


DATABASE_PATH = r"ISweep_backend\isweep.db"


def main() -> None:
    print()
    print("=" * 60)
    print("ISWEEP LOCAL PASSWORD RESET")
    print("=" * 60)
    print()

    email = input("Account email: ").strip().lower()

    if not email:
        print("Email is required.")
        return

    password = masked_password("New password: ")

    if not password:
        print("Password cannot be empty.")
        return

    confirmation = masked_password("Confirm password: ")

    if password != confirmation:
        print()
        print("Passwords did not match. Nothing was changed.")
        return

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        )

        user = cursor.fetchone()

        if not user:
            print()
            print(f"No local ISweep account found for {email}.")
            return

        password_hash = generate_password_hash(password)

        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?",
            (password_hash, email),
        )

        connection.commit()

        print()
        print("Password updated successfully.")
        print(f"Account: {email}")
        print()
        print("Your filters and preferences were not changed.")

    finally:
        connection.close()


if __name__ == "__main__":
    main()