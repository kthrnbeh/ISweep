import pytest  # Testing framework providing fixtures
import os  # Standard library for environment and file operations
import tempfile  # Provides temporary file utilities for isolated DBs


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    # Import app factory and database inside fixture to avoid import side effects at module load
    from app import app as flask_app  # Import the Flask app object
    from database import Database  # Import Database helper

    # Create a temporary database file for this test session
    db_fd, db_path = tempfile.mkstemp()  # mkstemp returns file descriptor and path

    # Set environment variable so app picks up the test DB path
    os.environ['DATABASE_PATH'] = db_path

    flask_app.config.update({
        'TESTING': True,  # Enable Flask testing flags (no error trapping, etc.)
    })

    # Initialize database instance and attach it to the Flask app for tests
    flask_app.database = Database(db_path)

    yield flask_app  # Provide the configured app to tests

    # Cleanup after tests finish
    if hasattr(flask_app, 'database'):
        delattr(flask_app, 'database')  # Remove test database attribute
    if hasattr(flask_app, 'analyzer'):
        delattr(flask_app, 'analyzer')  # Remove analyzer if attached during tests
    os.close(db_fd)  # Close temporary file descriptor
    os.unlink(db_path)  # Delete temporary database file
    if 'DATABASE_PATH' in os.environ:
        del os.environ['DATABASE_PATH']  # Remove env var to avoid leakage


@pytest.fixture
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()  # Return Flask test client bound to the app fixture


@pytest.fixture
def database():
    """Create a test database."""
    from database import Database  # Import Database within fixture to limit scope
    db_fd, db_path = tempfile.mkstemp()  # Allocate temporary DB file
    db = Database(db_path)  # Initialize Database pointing to temp file

    yield db  # Provide database to tests

    os.close(db_fd)  # Close temp file descriptor
    os.unlink(db_path)  # Remove temp DB file to clean up
