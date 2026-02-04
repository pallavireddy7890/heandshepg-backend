import sys
import os

# Add the current directory to sys.path so we can import app
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Profile, UserRole, AppRole
from app.utils.security import get_password_hash
import uuid

def create_admin_user(email, password, name):
    db: Session = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"User with email {email} already exists.")
            # Check if it has admin role
            admin_role = db.query(UserRole).filter(
                UserRole.user_id == existing_user.id, 
                UserRole.role == AppRole.admin
            ).first()
            if not admin_role:
                print(f"Adding admin role to existing user...")
                new_role = UserRole(user_id=existing_user.id, role=AppRole.admin)
                db.add(new_role)
                db.commit()
                print("Admin role added successfully.")
            else:
                print("User is already an admin.")
            return

        # Create new user
        hashed_password = get_password_hash(password)
        new_user = User(
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True
        )
        db.add(new_user)
        db.flush()  # To get the ID

        # Create profile
        new_profile = Profile(
            user_id=new_user.id,
            name=name,
            email=email,
            phone="0000000000"
        )
        db.add(new_profile)

        # Assign admin role
        new_role = UserRole(
            user_id=new_user.id,
            role=AppRole.admin
        )
        db.add(new_role)

        db.commit()
        print(f"Admin user created successfully: {email}")
        print(f"Password: {password}")

    except Exception as e:
        db.rollback()
        print(f"Error creating admin user: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user("admin@heandshepg.com", "Admin@123", "System Admin")
