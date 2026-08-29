"""
ISweep DVD - Password Input Helper

Provides a masked password prompt for local Windows development.

Unlike Python's standard getpass(), this shows "*" characters
while typing so the user can tell that keyboard input is being received.
"""

import sys


def masked_password(prompt: str = "Password: ") -> str:
    """
    Read a password while displaying "*" for each typed character.

    On Windows, uses msvcrt so the user gets visible feedback.
    On other systems, falls back to getpass().
    """

    if sys.platform.startswith("win"):
        import msvcrt

        print(prompt, end="", flush=True)

        characters: list[str] = []

        while True:
            char = msvcrt.getwch()

            if char in ("\r", "\n"):
                print()
                break

            if char == "\003":
                raise KeyboardInterrupt

            if char == "\b":
                if characters:
                    characters.pop()
                    print("\b \b", end="", flush=True)
                continue

            # Ignore special-key prefixes.
            if char in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue

            characters.append(char)
            print("*", end="", flush=True)

        return "".join(characters)

    from getpass import getpass

    return getpass(prompt)
