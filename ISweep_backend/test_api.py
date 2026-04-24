import json  # Standard library JSON handling for request/response bodies
import pytest  # Testing framework used for assertions and fixtures


def signup_and_get_token(client, email="user@example.com"):
    """Helper to create a user via auth and return (token, user_id)."""
    response = client.post('/auth/signup', json={'email': email, 'password': 'password123'})  # Call signup endpoint
    assert response.status_code in (200, 201)  # Ensure signup succeeded
    data = json.loads(response.data)  # Parse JSON response body
    return data['token'], data['user_id']  # Return token and user id tuple


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}  # Helper to build auth header for requests


class TestAPI:
    """Test the REST API endpoints."""

    def test_health_check(self, client):
        response = client.get('/api/health')  # Hit health check endpoint
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse JSON
        assert data['status'] == 'healthy'  # Verify status field
        assert data['service'] == 'ISweep Backend'  # Verify service name

    def test_health_root(self, client):
        response = client.get('/health')  # Hit root health endpoint
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse JSON
        assert data == {'status': 'ok'}  # Validate payload

    def test_create_user(self, client):
        response = client.post('/api/users', json={'username': 'testuser'})  # Create user without auth
        assert response.status_code == 201  # Expect created
        data = json.loads(response.data)  # Parse response
        assert data['username'] == 'testuser'  # Username echoed back
        assert 'user_id' in data  # Ensure user_id is present
        assert 'preferences' in data  # Ensure default preferences returned

    def test_create_duplicate_user(self, client):
        client.post('/api/users', json={'username': 'testuser'})  # First creation
        response = client.post('/api/users', json={'username': 'testuser'})  # Duplicate username
        assert response.status_code == 409  # Expect conflict

    def test_create_user_without_username(self, client):
        response = client.post('/api/users', json={})  # Missing username
        assert response.status_code == 400  # Expect bad request

    def test_get_preferences(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract user id

        response = client.get(f'/api/users/{user_id}/preferences')  # Fetch preferences
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse prefs
        assert 'categories' in data  # Categories should exist
        assert data['categories']['language']['enabled'] is True  # Language enabled default
        assert data['categories']['sexual']['enabled'] is True  # Sexual enabled default
        assert data['categories']['violence']['enabled'] is True  # Violence enabled default

    def test_get_preferences_nonexistent_user(self, client):
        response = client.get('/api/users/9999/preferences')  # Request prefs for missing user
        assert response.status_code == 404  # Expect not found

    def test_update_preferences(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract id

        update_data = {
            'enabled': True,
            'categories': {
                'language': {'enabled': False, 'action': 'mute', 'duration': 4},
                'violence': {'enabled': True, 'action': 'skip', 'duration': 10},
            },
            'sensitivity': 0.9,
        }  # Custom preference update
        response = client.put(f'/api/users/{user_id}/preferences', json=update_data)  # Update prefs
        assert response.status_code == 200  # Expect success

        data = json.loads(response.data)  # Parse response
        assert data['preferences']['categories']['language']['enabled'] is False  # Language disabled
        assert data['preferences']['categories']['violence']['duration'] == 10  # Violence duration updated

    def test_update_preferences_invalid_sensitivity(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Get id

        update_data = {'language_sensitivity': 'invalid'}  # Invalid payload
        response = client.put(f'/api/users/{user_id}/preferences', json=update_data)  # Send update
        assert response.status_code == 400  # Expect validation error

    def test_analyze_clean_content(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract id

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'This is a beautiful day with wonderful weather'
        })  # Analyze benign text
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'none'  # No action expected
        assert data['user_id'] == user_id  # User id echoed

    def test_analyze_profanity(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract id

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'This is damn stupid'
        })  # Analyze text with profanity
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'mute'  # Profanity should trigger mute

    def test_analyze_mild_profanity_hell(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract id

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'what the hell was that'
        })  # Analyze mild profanity
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'mute'  # Mild profanity triggers mute

    def test_analyze_violence(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract id

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'He was shot and killed in the fight'
        })  # Analyze violent text
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'fast_forward'  # Violence triggers fast-forward

    def test_analyze_sexual_content(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract id

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'The sexual scene was explicit'
        })  # Analyze sexual content
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'skip'  # Sexual content triggers skip

    def test_analyze_missing_fields(self, client):
        response = client.post('/api/analyze', json={'text': 'some text'})  # Missing user_id
        assert response.status_code == 400  # Expect bad request

        response = client.post('/api/analyze', json={'user_id': 1})  # Missing text
        assert response.status_code == 400  # Expect bad request

    def test_analyze_nonexistent_user(self, client):
        response = client.post('/api/analyze', json={'user_id': 9999, 'text': 'some text'})  # Nonexistent user
        assert response.status_code == 404  # Expect not found

    def test_analyze_with_disabled_filters(self, client):
        create_response = client.post('/api/users', json={'username': 'testuser'})  # Create user
        user_id = json.loads(create_response.data)['user_id']  # Extract id

        client.put(f'/api/users/{user_id}/preferences', json={
            'language_filter': False,
            'sexual_content_filter': False,
            'violence_filter': False
        })  # Disable all filters

        response = client.post('/api/analyze', json={
            'user_id': user_id,
            'text': 'This damn violent sexual content'
        })  # Analyze text that would otherwise trigger
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'none'  # No action because filters disabled

    def test_event_schema_and_priority(self, client):
        token, _ = signup_and_get_token(client, email='eventuser@example.com')  # Signup to get token

        response = client.post(
            '/event',
            json={'text': 'Explicit sexual content and sexual scene with a violent fight and strong language'},
            headers=auth_headers(token),
        )  # Call event endpoint with mixed content
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert set(data.keys()) == {'action', 'duration_seconds', 'matched_category', 'reason'}  # Validate schema
        assert data['action'] == 'skip'  # Sexual should take priority
        assert data['matched_category'] == 'sexual'  # Matched category is sexual
        assert isinstance(data['duration_seconds'], int) and data['duration_seconds'] > 0  # Duration is positive int
        assert isinstance(data['reason'], str) and data['reason']  # Reason string present

    def test_event_no_match(self, client):
        token, _ = signup_and_get_token(client, email='eventnomatch@example.com')  # Signup new user

        response = client.post('/event', json={'text': 'Lovely sunny afternoon with friends'}, headers=auth_headers(token))  # Benign text
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'none'  # No action
        assert data['duration_seconds'] == 0  # Zero duration
        assert data['matched_category'] is None  # No category matched
        assert data['reason'] == 'No match'  # Reason message

    def test_event_invalid_request(self, client):
        token, _ = signup_and_get_token(client, email='eventinvalid@example.com')  # Signup new user
        response = client.post('/event', json={'text': ''}, headers=auth_headers(token))  # Empty text
        assert response.status_code == 200  # Expect OK (handled gracefully)
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'none'  # No action
        assert data['duration_seconds'] == 0  # Zero duration
        assert data['matched_category'] is None  # No category
        assert data['reason'] == 'No text provided'  # Reason indicates missing text

    def test_event_unknown_user(self, client):
        response = client.post('/event', json={'text': 'anything'}, headers=auth_headers('invalid'))  # Invalid token
        assert response.status_code == 401  # Expect unauthorized

    def test_event_blocklist_match(self, client):
        token, _ = signup_and_get_token(client, email='blocklist@example.com')  # Signup user

        prefs_payload = {
            'enabled': True,
            'blocklist': {
                'enabled': True,
                'items': ['strip club'],
                'duration': 7,
            }
        }  # Preferences enabling blocklist with duration
        pref_res = client.put('/preferences', json=prefs_payload, headers=auth_headers(token))  # Update prefs
        assert pref_res.status_code == 200  # Expect success

        response = client.post(
            '/event',
            json={'text': 'He walked into a strip club downtown.'},
            headers=auth_headers(token),
        )  # Event text containing blocklisted phrase
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert data['action'] == 'mute'  # Blocklist triggers mute
        assert data['matched_category'] == 'blocklist'  # Matched category blocklist
        assert data['duration_seconds'] == 7  # Duration comes from prefs
        assert 'blocklist match' in data['reason']  # Reason mentions blocklist

    def test_event_caption_duration_override(self, client):
        token, _ = signup_and_get_token(client, email='duration@example.com')  # Signup user

        response = client.post(
            '/event',
            json={'text': 'shit damn fuck', 'caption_duration_seconds': 0.5},
            headers=auth_headers(token),
        )  # Event with profanity and short caption duration

        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse response
        assert set(data.keys()) == {'action', 'duration_seconds', 'matched_category', 'reason'}  # Validate schema
        assert data['action'] == 'mute'  # Profanity triggers mute
        assert data['matched_category'] == 'language'  # Matched category language
        assert data['duration_seconds'] == pytest.approx(0.65, abs=0.05)  # Duration scaled to caption length
        assert 0.2 <= data['duration_seconds'] <= 4.0  # Duration bounded within limits

    def test_event_endpoint_caption_duration_clamp_still_works(self, client):
        token, _ = signup_and_get_token(client, email='duration-clamp@example.com')

        response = client.post(
            '/event',
            json={'text': 'fuck', 'caption_duration_seconds': 10.0},
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert set(data.keys()) == {'action', 'duration_seconds', 'matched_category', 'reason'}
        assert data['action'] == 'mute'
        assert data['matched_category'] == 'language'
        assert data['duration_seconds'] == pytest.approx(2.5)
        assert isinstance(data['reason'], str) and data['reason']

    def test_videos_analyze_unavailable_transcript(self, client):
        token, _ = signup_and_get_token(client, email='video-unavailable@example.com')

        class AnalyzerStub:
            def analyze_video_markers(self, video_id, preferences):
                return {
                    'status': 'unavailable',
                    'source': None,
                    'events': [],
                    'cleaned_captions': [],
                    'clean_captions': [],
                    'failure_reason': 'transcript_unavailable',
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post('/videos/analyze', json={'video_id': 'no-transcript-video'}, headers=auth_headers(token))
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'unavailable'
        assert data['source'] is None
        assert data['events'] == []
        assert data['cleaned_captions'] == []
        assert data['clean_captions'] == []
        assert data['failure_reason'] == 'transcript_unavailable'

    def test_videos_analyze_ready_with_markers(self, client):
        token, _ = signup_and_get_token(client, email='video-ready@example.com')

        class AnalyzerStub:
            def analyze_video_markers(self, video_id, preferences):
                return {
                    'status': 'ready',
                    'source': 'transcript',
                    'events': [
                        {
                            'id': 'm1',
                            'start_seconds': 12.3,
                            'end_seconds': 13.6,
                            'action': 'mute',
                            'duration_seconds': 1.3,
                            'matched_category': 'language',
                            'reason': 'test marker',
                        }
                    ],
                    'cleaned_captions': [
                        {
                            'start_seconds': 12.3,
                            'end_seconds': 13.6,
                            'text': 'What the heck is going on?',
                            'clean_text': 'What the ____ is going on?',
                        }
                    ],
                    'clean_captions': [
                        {
                            'start_seconds': 12.3,
                            'end_seconds': 13.6,
                            'text': 'What the heck is going on?',
                            'clean_text': 'What the ____ is going on?',
                        }
                    ],
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post('/videos/analyze', json={'video_id': 'abc123'}, headers=auth_headers(token))
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ready'
        assert data['source'] == 'transcript'
        assert len(data['events']) == 1
        assert data['events'][0]['id'] == 'm1'
        assert len(data['cleaned_captions']) == 1
        assert data['cleaned_captions'][0]['clean_text'] == 'What the ____ is going on?'
        assert data['clean_captions'] == data['cleaned_captions']
        assert data['failure_reason'] is None
