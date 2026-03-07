import pytest
import os
import tempfile

@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    # Import app first
    from app import app as flask_app
    from database import Database
    
    # Create a temporary database for testing
    db_fd, db_path = tempfile.mkstemp()
    
    # Set environment variable for testing
    os.environ['DATABASE_PATH'] = db_path
    
    flask_app.config.update({
        'TESTING': True,
    })
    
    # Initialize database and attach to app
    flask_app.database = Database(db_path)
    
    yield flask_app
    
    # Cleanup
    if hasattr(flask_app, 'database'):
        delattr(flask_app, 'database')
    if hasattr(flask_app, 'analyzer'):
        delattr(flask_app, 'analyzer')
    os.close(db_fd)
    os.unlink(db_path)
    if 'DATABASE_PATH' in os.environ:
        del os.environ['DATABASE_PATH']

@pytest.fixture
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()

@pytest.fixture
def database():
    """Create a test database."""
    from database import Database
    db_fd, db_path = tempfile.mkstemp()
    db = Database(db_path)
    
    yield db
    
    os.close(db_fd)
    os.unlink(db_path)
