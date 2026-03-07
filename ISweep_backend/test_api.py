import json
import pytest


def signup_and_get_token(client, email="user@example.com"):
    """Helper to create a user via auth and return (token, user_id)."""
    response = client.post('/auth/signup', json={'email': email, 'password': 'password123'})
    assert response.status_code in (200, 201)
    data = json.loads(response.data)
    return data['token'], data['user_id']


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestAPI:
    """Test the REST API endpoints."""

    def test_health_check(self, client):
        response = client.get('/api/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert data['service'] == 'ISweep Backend'

    def test_health_root(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == {'status': 'ok'}

    def test_create_user(self, client):
        response = client.post('/api/users', json={'username': 'testuser'})
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['username'] == 'testuser'
        assert 'user_id' in data
        assert 'preferences' in data

    def test_create_duplicate_user(self, client):
        client.post('/api/users', json={'username': 'testuser'})
        response = client.post('/api/users', json={'username': 'testuser'})
        assert response.status_code == 409

    def test_create_user_without_username(self, client):
        response = client.post('/api/users', json={})
        assert response.status_code == 400

    def test_get_preferences(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        response = client.get(f'/api/users/{user_id}/preferences')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'categories' in data
        assert data['categories']['language']['enabled'] is True
        assert data['categories']['sexual']['enabled'] is True
        assert data['categories']['violence']['enabled'] is True

    def test_get_preferences_nonexistent_user(self, client):
        response = client.get('/api/users/9999/preferences')
        assert response.status_code == 404

    def test_update_preferences(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        update_data = {
            'enabled': True,
            'categories': {
                'language': {'enabled': False, 'action': 'mute', 'duration': 4},
                'violence': {'enabled': True, 'action': 'skip', 'duration': 10},
            },
            'sensitivity': 0.9,
        }
        response = client.put(f'/api/users/{user_id}/preferences', json=update_data)
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['preferences']['categories']['language']['enabled'] is False
        assert data['preferences']['categories']['violence']['duration'] == 10

    def test_update_preferences_invalid_sensitivity(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        update_data = {'language_sensitivity': 'invalid'}
        response = client.put(f'/api/users/{user_id}/preferences', json=update_data)
        assert response.status_code == 400

    def test_analyze_clean_content(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'This is a beautiful day with wonderful weather'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'none'
        assert data['user_id'] == user_id

    def test_analyze_profanity(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'This is damn stupid'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'mute'

    def test_analyze_mild_profanity_hell(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'what the hell was that'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'mute'

    def test_analyze_violence(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'He was shot and killed in the fight'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'fast_forward'

    def test_analyze_sexual_content(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'The sexual scene was explicit'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'skip'

    def test_analyze_missing_fields(self, client):
        response = client.post('/api/analyze', json={'text': 'some text'})
        assert response.status_code == 400

        response = client.post('/api/analyze', json={'user_id': 1})
        assert response.status_code == 400

    def test_analyze_nonexistent_user(self, client):
        response = client.post('/api/analyze', json={'user_id': 9999, 'text': 'some text'})
        assert response.status_code == 404

    def test_analyze_with_disabled_filters(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})
        user_id = json.loads(create_response.data)['user_id']

        client.put(f'/api/users/{user_id}/preferences', json={
            'language_filter': False,
            'sexual_content_filter': False,
            'violence_filter': False
        })

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'This damn violent sexual content'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'none'

    def test_event_schema_and_priority(self, client):
        token, _ = signup_and_get_token(client, email='eventuser@example.com')

        response = client.post(
            '/event',
            json={'text': 'Explicit sexual content and sexual scene with a violent fight and strong language'},
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert set(data.keys()) == {'action', 'duration_seconds', 'matched_category', 'reason'}
        assert data['action'] == 'skip'
        assert data['matched_category'] == 'sexual'
        assert isinstance(data['duration_seconds'], int) and data['duration_seconds'] > 0
        assert isinstance(data['reason'], str) and data['reason']

    def test_event_no_match(self, client):
        token, _ = signup_and_get_token(client, email='eventnomatch@example.com')

        response = client.post('/event', json={'text': 'Lovely sunny afternoon with friends'}, headers=auth_headers(token))
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'none'
        assert data['duration_seconds'] == 0
        assert data['matched_category'] is None
        assert data['reason'] == 'No match'

    def test_event_invalid_request(self, client):
        token, _ = signup_and_get_token(client, email='eventinvalid@example.com')
        response = client.post('/event', json={'text': ''}, headers=auth_headers(token))
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'none'
        assert data['duration_seconds'] == 0
        assert data['matched_category'] is None
        assert data['reason'] == 'No text provided'

    def test_event_unknown_user(self, client):
        response = client.post('/event', json={'text': 'anything'}, headers=auth_headers('invalid'))
        assert response.status_code == 401

    def test_event_blocklist_match(self, client):
        token, _ = signup_and_get_token(client, email='blocklist@example.com')

        prefs_payload = {
            'enabled': True,
            'blocklist': {
                'enabled': True,
                'items': ['strip club'],
                'duration': 7,
            }
        }
        pref_res = client.put('/preferences', json=prefs_payload, headers=auth_headers(token))
        assert pref_res.status_code == 200

        response = client.post(
            '/event',
            json={'text': 'He walked into a strip club downtown.'},
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['action'] == 'mute'
        assert data['matched_category'] == 'blocklist'
        assert data['duration_seconds'] == 7
        assert 'blocklist match' in data['reason']

    def test_event_caption_duration_override(self, client):
        token, _ = signup_and_get_token(client, email='duration@example.com')

        response = client.post(
            '/event',
            json={'text': 'shit damn fuck', 'caption_duration_seconds': 0.5},
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert set(data.keys()) == {'action', 'duration_seconds', 'matched_category', 'reason'}
        assert data['action'] == 'mute'
        assert data['matched_category'] == 'language'
        assert data['duration_seconds'] == pytest.approx(0.65, abs=0.05)
        assert 0.2 <= data['duration_seconds'] <= 4.0
