#!/usr/bin/env python3
"""
CLI Script to create or update an Admin user in the database.
Reads the database connection URL from the DATABASE_URL environment variable.
Usage:
    python scripts/create_admin.py --email admin@example.com --password mysecurepassword --name "Admin Name"
"""
import os
import sys
import argparse
from dotenv import load_dotenv

# Load environment variables (e.g., DATABASE_URL, SECRET_KEY)
load_dotenv()

# Add the project root directory to the python path so imports work correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import User, Profile, UserRole, AppRole
from app.utils.security import get_password_hash, validate_password_strength

def parse_arguments():
    parser = argparse.ArgumentParser(description="Create or upgrade an Admin user in the database.")
    parser.add_argument("--email", type=str, help="Email of the admin user.")
    parser.add_argument("--password", type=str, help="Password of the admin user.")
    parser.add_argument("--name", type=str, default="System Admin", help="Full name of the admin.")
    return parser.parse_args()

def main():
    args = parse_arguments()

    # Get values from CLI arguments or environment variables
    email = args.email or os.environ.get("ADMIN_EMAIL")
    password = args.password or os.environ.get("ADMIN_PASSWORD")
    name = args.name

    # Check if terminal is interactive
    is_interactive = sys.stdin.isatty()
    
    if not email:
        if is_interactive:
            email = input("Enter Admin Email: ").strip()
        else:
            email = "admin@heandshepg.com"
            print(f"No email specified. Falling back to default: {email}")
            
    if not password:
        if is_interactive:
            import getpass
            while True:
                password = getpass.getpass("Enter Admin Password: ")
                confirm = getpass.getpass("Confirm Admin Password: ")
                if password == confirm:
                    try:
                        validate_password_strength(password)
                        break
                    except ValueError as e:
                        print(f"Password weak: {e}. Try again.")
                else:
                    print("Passwords do not match. Try again.")
        else:
            password = "AdminPass123!"
            print(f"No password specified. Falling back to default: {password}")

    # Validate email
    if not email or "@" not in email:
        print(f"ERROR: '{email}' is not a valid email address.")
        sys.exit(1)

    # Validate password strength (only validate for non-default passwords to avoid failing on fallback)
    if password != "AdminPass123!":
        try:
            validate_password_strength(password)
        except ValueError as e:
            print(f"ERROR: Password validation failed: {e}")
            sys.exit(1)

    print(f"Connecting to database to setup admin '{email}'...")
    db = SessionLocal()
    try:
        # 1. Create or update user
        user = db.query(User).filter(User.email == email.lower().strip()).first()
        if not user:
            print(f"User '{email}' not found. Creating a new account...")
            hashed_pw = get_password_hash(password)
            user = User(
                email=email.lower().strip(),
                hashed_password=hashed_pw,
                is_active=True,
                is_verified=True
            )
            db.add(user)
            db.flush()  # Generate user ID
            
            # Create corresponding profile
            profile = Profile(
                user_id=user.id,
                name=name,
                email=email.lower().strip(),
                profile_verification_status="verified"
            )
            db.add(profile)
            print(f"  [OK] User account and profile created.")
        else:
            print(f"User '{email}' already exists. Upgrading to admin status...")
            user.is_active = True
            user.is_verified = True
            
            # Update profile if name was specified
            profile = db.query(Profile).filter(Profile.user_id == user.id).first()
            if profile:
                profile.profile_verification_status = "verified"
                if name and name != "System Admin":
                    profile.name = name
            else:
                profile = Profile(
                    user_id=user.id,
                    name=name,
                    email=email.lower().strip(),
                    profile_verification_status="verified"
                )
                db.add(profile)

        # 2. Check and assign Admin role
        role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
        if role:
            old_role = role.role.value
            role.role = AppRole.admin
            print(f"  [OK] Role updated from '{old_role}' to 'admin'.")
        else:
            role = UserRole(user_id=user.id, role=AppRole.admin)
            db.add(role)
            print(f"  [OK] Role 'admin' assigned to user.")

        db.commit()
        print(f"\n[SUCCESS] Admin user '{email}' is successfully configured in the database!")
        
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] An error occurred during database transaction: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
