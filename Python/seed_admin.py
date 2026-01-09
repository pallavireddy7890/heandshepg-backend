"""Database seed script to create initial admin user."""
from app.database import SessionLocal, engine, Base
from app.models import User, Profile, UserRole, AppRole
from app.utils.security import get_password_hash


def create_admin_user():
    """Create admin user in database."""
    db = SessionLocal()
    
    try:
        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        
        # NEW ADMIN CREDENTIALS
        admin_email = "superadmin@heandshepg.com"
        admin_password = "SuperAdmin@2024"
        admin_name = "Super Admin"
        
        # Check if admin already exists
        existing_user = db.query(User).filter(User.email == admin_email).first()
        
        if existing_user:
            print(f"User {admin_email} already exists. Updating role to admin...")
            # Update role to admin
            user_role = db.query(UserRole).filter(UserRole.user_id == existing_user.id).first()
            if user_role:
                user_role.role = AppRole.admin
            else:
                user_role = UserRole(user_id=existing_user.id, role=AppRole.admin)
                db.add(user_role)
            db.commit()
            print(f"✅ Updated {admin_email} to admin role")
        else:
            print(f"Creating new admin user: {admin_email}")
            
            # Create user
            hashed_password = get_password_hash(admin_password)
            new_user = User(
                email=admin_email,
                hashed_password=hashed_password,
                is_active=True,
                is_verified=True,
            )
            db.add(new_user)
            db.flush()
            
            # Create profile
            profile = Profile(
                user_id=new_user.id,
                name=admin_name,
                email=admin_email,
            )
            db.add(profile)
            
            # Create admin role
            admin_role = UserRole(user_id=new_user.id, role=AppRole.admin)
            db.add(admin_role)
            
            db.commit()
            print(f"✅ Created admin user successfully!")
        
        print("\n" + "="*50)
        print("ADMIN CREDENTIALS")
        print("="*50)
        print(f"Email:    {admin_email}")
        print(f"Password: {admin_password}")
        print("="*50)
        print("\n⚠️  IMPORTANT: Change the password after first login!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()
