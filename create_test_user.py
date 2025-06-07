from app import app, db
from database_model import User

def create_test_user():
    with app.app_context():
        # Check if test user already exists
        test_user = User.query.filter_by(email='test@example.com').first()
        if test_user:
            print("Test user already exists!")
            return

        # Create new test user
        test_user = User(
            username='testuser',
            email='test@example.com'
        )
        test_user.set_passsword('test123')  # Note: there's a typo in the method name in the model

        # Add to database
        db.session.add(test_user)
        db.session.commit()
        print("Test user created successfully!")

if __name__ == '__main__':
    create_test_user() 