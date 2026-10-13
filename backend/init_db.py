from backend.db.database import Base, engine, init_db

if __name__ == "__main__":
    print("Creating database tables...")
    init_db()
    print("Database initialized successfully!")
