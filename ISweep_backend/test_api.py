import json  # Standard library JSON handling for request/response bodies
import base64
import math
import wave
from io import BytesIO
from pathlib import Path
import pytest  # Testing framework used for assertions and fixtures
import numpy as np


def signup_and_get_token(client, email="user@example.com"):
    """Helper to create a user via auth and return (token, user_id)."""
    response = client.post('/auth/signup', json={'email': email, 'password': 'password123'})  # Call signup endpoint
    assert response.status_code in (200, 201)  # Ensure signup succeeded
    data = json.loads(response.data)  # Parse JSON response body
    return data['token'], data['user_id']  # Return token and user id tuple


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}  # Helper to build auth header for requests


def make_wav_base64(samples, sample_rate=16000):
    pcm = np.asarray(samples, dtype=np.float32)
    if pcm.ndim != 1:
        pcm = pcm.reshape(-1)
    pcm = np.clip(pcm, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with BytesIO() as wav_buffer:
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sample_rate))
            wav_file.writeframes(pcm16.tobytes())
        return base64.b64encode(wav_buffer.getvalue()).decode('ascii')


def make_silent_wav_base64(duration_seconds=0.5, sample_rate=16000):
    count = int(max(duration_seconds, 0.0) * sample_rate)
    return make_wav_base64(np.zeros(count, dtype=np.float32), sample_rate=sample_rate)


def make_tone_wav_base64(duration_seconds=0.5, sample_rate=16000, hz=440.0, amplitude=0.2):
    count = int(max(duration_seconds, 0.0) * sample_rate)
    t = np.arange(count, dtype=np.float32) / float(sample_rate)
    samples = amplitude * np.sin(2.0 * math.pi * float(hz) * t)
    return make_wav_base64(samples, sample_rate=sample_rate)


class TestAPI:
    """Test the REST API endpoints."""

    def test_dependency_notes_file_exists(self):
        notes_path = Path(__file__).resolve().parents[1] / 'docs' / 'dependency_notes.md'
        assert notes_path.exists()
        notes = notes_path.read_text(encoding='utf-8')
        assert 'faster-whisper' in notes
        assert 'must never edit or redistribute video/audio' in notes.lower()
        assert 'Do not copy YouTube captions' in notes

    def test_health_check(self, client):
        response = client.get('/api/health')  # Hit health check endpoint
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse JSON
        assert data['status'] == 'healthy'  # Verify status field
        assert data['service'] == 'ISweep Backend'  # Verify service name

    def test_cache_fingerprint_differs_when_stt_mode_changes(self):
        from app import build_preferences_fingerprint

        prefs = {
            'enabled': True,
            'categories': {'language': {'enabled': True, 'action': 'mute', 'duration': 4}},
        }

        no_stt = build_preferences_fingerprint(prefs, {'enabled': False, 'model': None})
        with_stt = build_preferences_fingerprint(prefs, {'enabled': True, 'model': 'base'})

        assert isinstance(no_stt, str)
        assert isinstance(with_stt, str)
        assert no_stt != with_stt

    def test_health_root(self, client):
        response = client.get('/health')  # Hit root health endpoint
        assert response.status_code == 200  # Expect OK
        data = json.loads(response.data)  # Parse JSON
        assert data['status'] == 'ok'  # Validate payload
        assert 'stt_enabled' in data

    def test_auth_register_alias_creates_account_and_returns_token(self, client):
        response = client.post('/auth/register', json={'email': 'register-alias@example.com', 'password': 'Password123!'})
        assert response.status_code in (200, 201)
        data = json.loads(response.data)
        assert isinstance(data.get('token'), str) and data['token']
        assert isinstance(data.get('user_id'), int)

    def test_auth_login_success_returns_token(self, client):
        client.post('/auth/signup', json={'email': 'login-success@example.com', 'password': 'Password123!'})
        response = client.post('/auth/login', json={'email': 'login-success@example.com', 'password': 'Password123!'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data.get('token'), str) and data['token']
        assert isinstance(data.get('user_id'), int)

    def test_auth_login_invalid_credentials_returns_clear_401_json(self, client):
        client.post('/auth/signup', json={'email': 'login-fail@example.com', 'password': 'Password123!'})
        response = client.post('/auth/login', json={'email': 'login-fail@example.com', 'password': 'WrongPass123!'})
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data.get('error') == 'Invalid credentials'

    def test_auth_user_record_persists_in_local_sqlite(self, client):
        email = 'persist-user@example.com'
        password = 'Password123!'
        signup = client.post('/auth/signup', json={'email': email, 'password': password})
        assert signup.status_code in (200, 201)

        db = client.application.database
        user = db.get_user_by_email(email)
        assert user is not None
        assert user.get('email') == email

        login = client.post('/auth/login', json={'email': email, 'password': password})
        assert login.status_code == 200

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
        assert data['cached'] is False

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
                            'clean_resume_time': 13.1,
                            'words': [
                                {'word': 'What', 'start': 12.3, 'end': 12.5},
                                {'word': 'the', 'start': 12.5, 'end': 12.6},
                                {'word': 'heck', 'start': 12.6, 'end': 12.9},
                                {'word': 'is', 'start': 12.9, 'end': 13.0},
                            ],
                        }
                    ],
                    'clean_captions': [
                        {
                            'start_seconds': 12.3,
                            'end_seconds': 13.6,
                            'text': 'What the heck is going on?',
                            'clean_text': 'What the ____ is going on?',
                            'clean_resume_time': 13.1,
                            'words': [
                                {'word': 'What', 'start': 12.3, 'end': 12.5},
                                {'word': 'the', 'start': 12.5, 'end': 12.6},
                                {'word': 'heck', 'start': 12.6, 'end': 12.9},
                                {'word': 'is', 'start': 12.9, 'end': 13.0},
                            ],
                        }
                    ],
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post('/videos/analyze', json={'video_id': 'abc123'}, headers=auth_headers(token))
        assert response.status_code == 200
        data = json.loads(response.data)
        assert set(data.keys()) == {
            'status',
            'source',
            'events',
            'cleaned_captions',
            'clean_captions',
            'failure_reason',
            'cached',
        }
        assert data['status'] == 'ready'
        assert data['source'] == 'transcript'
        assert len(data['events']) == 1
        assert data['events'][0]['id'] == 'm1'
        assert len(data['cleaned_captions']) == 1
        assert data['cleaned_captions'][0]['clean_text'] == 'What the ____ is going on?'
        assert data['cleaned_captions'][0]['clean_resume_time'] == 13.1
        assert len(data['cleaned_captions'][0]['words']) == 4
        assert data['cleaned_captions'][0]['words'][0]['word'] == 'What'
        assert data['clean_captions'] == data['cleaned_captions']
        assert data['failure_reason'] is None
        assert data['cached'] is False

    def test_videos_analyze_uses_cache_on_second_call(self, client):
        token, _ = signup_and_get_token(client, email='video-cache-hit@example.com')

        class AnalyzerStub:
            def __init__(self):
                self.calls = 0

            def analyze_video_markers(self, video_id, preferences):
                self.calls += 1
                return {
                    'status': 'ready',
                    'source': 'transcript',
                    'events': [{'id': 'cached-1', 'start_seconds': 1.0, 'end_seconds': 2.0, 'action': 'mute', 'duration_seconds': 1.0, 'matched_category': 'language', 'reason': 'cached'}],
                    'cleaned_captions': [{'start_seconds': 1.0, 'end_seconds': 2.0, 'text': 'a', 'clean_text': 'a'}],
                    'clean_captions': [{'start_seconds': 1.0, 'end_seconds': 2.0, 'text': 'a', 'clean_text': 'a'}],
                    'failure_reason': None,
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub

        first = client.post('/videos/analyze', json={'video_id': 'cached-video'}, headers=auth_headers(token))
        assert first.status_code == 200
        first_data = json.loads(first.data)
        assert first_data['cached'] is False
        assert stub.calls == 1

        second = client.post('/videos/analyze', json={'video_id': 'cached-video'}, headers=auth_headers(token))
        assert second.status_code == 200
        second_data = json.loads(second.data)
        assert second_data['cached'] is True
        assert second_data['events'][0]['id'] == 'cached-1'
        assert stub.calls == 1

    def test_videos_analyze_force_refresh_bypasses_cache(self, client):
        token, _ = signup_and_get_token(client, email='video-cache-force@example.com')

        class AnalyzerStub:
            def __init__(self):
                self.calls = 0

            def analyze_video_markers(self, video_id, preferences):
                self.calls += 1
                return {
                    'status': 'ready',
                    'source': 'transcript',
                    'events': [{'id': f'force-{self.calls}', 'start_seconds': 1.0, 'end_seconds': 2.0, 'action': 'mute', 'duration_seconds': 1.0, 'matched_category': 'language', 'reason': 'force'}],
                    'cleaned_captions': [],
                    'clean_captions': [],
                    'failure_reason': None,
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub

        first = client.post('/videos/analyze', json={'video_id': 'force-video'}, headers=auth_headers(token))
        assert first.status_code == 200
        assert json.loads(first.data)['cached'] is False

        second = client.post('/videos/analyze', json={'video_id': 'force-video', 'force_refresh': True}, headers=auth_headers(token))
        second_data = json.loads(second.data)
        assert second.status_code == 200
        assert second_data['cached'] is False
        assert second_data['events'][0]['id'] == 'force-2'
        assert stub.calls == 2

    def test_videos_analyze_cache_respects_preferences_fingerprint(self, client):
        token, user_id = signup_and_get_token(client, email='video-cache-prefs@example.com')

        class AnalyzerStub:
            def __init__(self):
                self.calls = 0

            def analyze_video_markers(self, video_id, preferences):
                self.calls += 1
                duration = preferences.get('categories', {}).get('language', {}).get('duration', 4)
                return {
                    'status': 'ready',
                    'source': 'transcript',
                    'events': [{'id': f'prefs-{duration}', 'start_seconds': 1.0, 'end_seconds': 2.0, 'action': 'mute', 'duration_seconds': 1.0, 'matched_category': 'language', 'reason': 'prefs'}],
                    'cleaned_captions': [],
                    'clean_captions': [],
                    'failure_reason': None,
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub

        first = client.post('/videos/analyze', json={'video_id': 'prefs-video'}, headers=auth_headers(token))
        assert first.status_code == 200
        assert json.loads(first.data)['cached'] is False
        assert stub.calls == 1

        db = client.application.database
        prefs = db.get_user_preferences(user_id)
        prefs['categories']['language']['duration'] = 9
        assert db.update_user_preferences(user_id, prefs) is True

        second = client.post('/videos/analyze', json={'video_id': 'prefs-video'}, headers=auth_headers(token))
        second_data = json.loads(second.data)
        assert second.status_code == 200
        assert second_data['cached'] is False
        assert second_data['events'][0]['id'] == 'prefs-9'
        assert stub.calls == 2

    def test_audio_analyze_returns_cleaned_captions_and_cached_false(self, client):
        token, _ = signup_and_get_token(client, email='audio-ready@example.com')

        class AnalyzerStub:
            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [{
                        'id': 'a1',
                        'start_seconds': 4.2,
                        'end_seconds': 4.8,
                        'action': 'mute',
                        'duration_seconds': 0.6,
                        'matched_category': 'language',
                        'reason': 'test',
                        'blocked_word_start': 4.2,
                        'clean_resume_time': 4.8,
                    }],
                    'cleaned_captions': [{
                        'start_seconds': 4.0,
                        'end_seconds': 5.0,
                        'text': 'what the heck',
                        'clean_text': 'what the ____',
                    }],
                    'text': 'what the heck',
                    'clean_text': 'what the ____',
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/audio/analyze',
            json={
                'video_id': 'audio-vid-1',
                'audio_chunk': 'ZmFrZQ==',
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 4.0,
                'chunk_end_seconds': 5.0,
            },
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ready'
        assert data['source'] == 'audio_stt'
        assert data['cached'] is False
        assert len(data['events']) == 1
        assert len(data['cleaned_captions']) == 1
        assert data['clean_captions'] == data['cleaned_captions']
        assert data['text'] == 'what the heck'
        assert data['clean_text'] == 'what the ____'

    def test_audio_analyze_invalid_base64_returns_audio_decode_failed(self, client):
        token, _ = signup_and_get_token(client, email='audio-invalid@example.com')

        response = client.post(
            '/audio/analyze',
            json={
                'video_id': 'audio-invalid-1',
                'audio_chunk': '!!!not-valid-base64!!!',
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 4.0,
                'chunk_end_seconds': 5.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'error'
        assert data['failure_reason'] == 'audio_decode_failed'
        assert data['cached'] is False

    def test_audio_analyze_chunk_returns_live_events(self, client):
        token, _ = signup_and_get_token(client, email='audio-live-chunk@example.com')

        class AnalyzerStub:
            def analyze_audio_chunk_bytes(self, audio_bytes, start_time, preferences, video_id='', chunk_duration_sec=None):
                return {
                    'events': [{
                        'start_seconds': 123.62,
                        'end_seconds': 124.10,
                        'action': 'mute',
                        'duration_seconds': 0.48,
                        'matched_category': 'language',
                        'reason': 'audio chunk match',
                        'source': 'audio',
                        'blocked_word_start': 123.62,
                        'clean_resume_time': 124.10,
                    }],
                    'cleaned_text': 'What the ____ is going on',
                    'words': [{'word': 'What', 'start': 123.5, 'end': 123.6}],
                    'source': 'audio',
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()

        response = client.post(
            '/audio/analyze_chunk',
            json={
                'video_id': 'vid-live-1',
                'audio_base64': 'ZmFrZQ==',
                'start_time': 123.45,
            },
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['source'] == 'audio'
        assert data['failure_reason'] is None
        assert isinstance(data['events'], list) and len(data['events']) == 1
        assert data['events'][0]['start_seconds'] == pytest.approx(123.62)
        assert data['cleaned_text'] == 'What the ____ is going on'

    def test_audio_analyze_chunk_stt_disabled_returns_empty_events(self, client):
        token, _ = signup_and_get_token(client, email='audio-live-disabled@example.com')

        class AnalyzerStub:
            def analyze_audio_chunk_bytes(self, audio_bytes, start_time, preferences, video_id='', chunk_duration_sec=None):
                return {
                    'events': [],
                    'cleaned_text': '',
                    'words': [],
                    'source': 'audio',
                    'failure_reason': 'stt_disabled',
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/audio/analyze_chunk',
            json={
                'video_id': 'vid-live-2',
                'audio_base64': 'ZmFrZQ==',
                'start_time': 55.0,
            },
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['events'] == []
        assert data['failure_reason'] == 'stt_disabled'

    def test_captions_transcribe_disabled_returns_safe_response(self, client):
        token, _ = signup_and_get_token(client, email='captions-transcribe-disabled@example.com')

        class AnalyzerStub:
            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'unavailable',
                    'source': 'audio_chunk',
                    'events': [],
                    'cleaned_captions': [],
                    'failure_reason': 'stt_disabled',
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-1',
                'audio_chunk': 'ZmFrZQ==',
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 1.0,
                'chunk_end_seconds': 2.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['text'] == ''
        assert data['source'] == 'audio_stt_disabled'
        assert data['confidence'] == 0.0
        assert data['reason'] == 'Speech-to-text is not enabled'
        assert data['failure_reason'] == 'stt_disabled'
        assert data['stt_status'] == 'disabled'
        assert data['stt_error'] == 'stt_disabled'

    def test_captions_transcribe_unavailable_returns_unavailable_source(self, client):
        token, _ = signup_and_get_token(client, email='captions-transcribe-unavailable@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base'

            def _get_or_create_stt_adapter(self):
                return object()

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'error',
                    'source': 'audio_chunk',
                    'events': [],
                    'cleaned_captions': [],
                    'failure_reason': 'stt_unavailable',
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-2',
                'audio_chunk': 'ZmFrZQ==',
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 5.0,
                'chunk_end_seconds': 6.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['source'] == 'audio_stt_unavailable'
        assert data['reason'] == 'Speech-to-text is unavailable'
        assert data['failure_reason'] == 'stt_unavailable'
        assert data['stt_status'] == 'model_unavailable'
        assert data['stt_error'] == 'stt_unavailable'

    def test_captions_transcribe_empty_text_returns_silent_audio_status(self, client):
        token, _ = signup_and_get_token(client, email='captions-transcribe-silence@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base'

            def _get_or_create_stt_adapter(self):
                return object()

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [],
                    'cleaned_captions': [],
                    'text': '',
                    'clean_text': '',
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-silence',
                'audio_chunk': make_silent_wav_base64(),
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 7.0,
                'chunk_end_seconds': 8.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['text'] == ''
        assert data['source'] == 'silence'
        assert data['confidence'] == 0.0
        assert data['stt_status'] == 'silent_audio'
        assert data['stt_error'] is None

    def test_captions_transcribe_non_silent_stt_result_returns_text_words_and_ok_status(self, client):
        token, _ = signup_and_get_token(client, email='captions-word-timestamps@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base'

            def _get_or_create_stt_adapter(self):
                return object()

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [],
                    'cleaned_captions': [
                        {
                            'start_seconds': 1.0,
                            'end_seconds': 2.0,
                            'text': 'go to hell now',
                            'clean_text': 'go to ___ now',
                            'words': [
                                {'word': 'go', 'start': 1.0, 'end': 1.2},
                                {'word': 'to', 'start': 1.2, 'end': 1.3},
                                {'word': 'hell', 'start': 1.3, 'end': 1.7},
                                {'word': 'now', 'start': 1.7, 'end': 2.0},
                            ],
                        }
                    ],
                    'text': 'go to hell now',
                    'clean_text': 'go to ___ now',
                    'words': [
                        {'word': 'go', 'start': 1.0, 'end': 1.2},
                        {'word': 'to', 'start': 1.2, 'end': 1.3},
                        {'word': 'hell', 'start': 1.3, 'end': 1.7},
                        {'word': 'now', 'start': 1.7, 'end': 2.0},
                    ],
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-words',
                'audio_chunk': make_tone_wav_base64(),
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 1.0,
                'chunk_end_seconds': 2.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['source'] == 'audio_stt_live'
        assert isinstance(data.get('words'), list)
        assert len(data['words']) == 4
        assert data['words'][2]['word'].lower() == 'hell'
        assert isinstance(data.get('word_timestamps'), list)
        assert len(data['word_timestamps']) == 4
        assert data['word_timestamps'][2]['word'].lower() == 'hell'
        assert data['stt_status'] == 'ok'
        assert data['stt_error'] is None

    def test_captions_transcribe_exception_returns_transcription_error_status(self, client):
        token, _ = signup_and_get_token(client, email='captions-transcribe-exception@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base'

            def _get_or_create_stt_adapter(self):
                return object()

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                raise RuntimeError('mock transcription explosion')

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-exception',
                'audio_chunk': make_tone_wav_base64(),
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 10.0,
                'chunk_end_seconds': 11.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['text'] == ''
        assert data['words'] == []
        assert data['word_timestamps'] == []
        assert data['stt_status'] == 'transcription_error'
        assert isinstance(data['stt_error'], str)
        assert 'mock transcription explosion' in data['stt_error']

    def test_captions_transcribe_rolling_text_does_not_repeat_previous_words(self, client):
        import app as app_module
        token, _ = signup_and_get_token(client, email='captions-rolling-dedupe@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base.en'

            def __init__(self):
                self.calls = 0

            def _get_or_create_stt_adapter(self):
                return object()

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                self.calls += 1
                if self.calls == 1:
                    words = [
                        {'word': 'hello', 'start': 1.0, 'end': 1.2},
                        {'word': 'world', 'start': 1.2, 'end': 1.4},
                        {'word': 'from', 'start': 1.4, 'end': 1.55},
                        {'word': 'isweep', 'start': 1.55, 'end': 1.8},
                    ]
                    text = 'hello world from isweep'
                else:
                    words = [
                        {'word': 'world', 'start': 1.2, 'end': 1.4},
                        {'word': 'from', 'start': 1.4, 'end': 1.55},
                        {'word': 'isweep', 'start': 1.55, 'end': 1.8},
                        {'word': 'now', 'start': 1.8, 'end': 2.0},
                        {'word': 'faster', 'start': 2.0, 'end': 2.3},
                    ]
                    text = 'world from isweep now faster'
                return {
                    'status': 'ready',
                    'source': 'audio_stt_live',
                    'events': [],
                    'cleaned_captions': [],
                    'text': text,
                    'clean_text': text,
                    'words': words,
                    'failure_reason': None,
                }

        original_interval = app_module.ROLLING_TRANSCRIBE_INTERVAL_MS
        app_module.ROLLING_TRANSCRIBE_INTERVAL_MS = 0
        client.application.analyzer = AnalyzerStub()
        try:
            first = client.post(
                '/captions/transcribe',
                json={
                    'video_id': 'captions-rolling-dedupe-1',
                    'audio_chunk': make_tone_wav_base64(),
                    'mime_type': 'audio/wav',
                    'chunk_start_seconds': 1.0,
                    'chunk_end_seconds': 2.0,
                },
                headers=auth_headers(token),
            )
            second = client.post(
                '/captions/transcribe',
                json={
                    'video_id': 'captions-rolling-dedupe-1',
                    'audio_chunk': make_tone_wav_base64(),
                    'mime_type': 'audio/wav',
                    'chunk_start_seconds': 1.35,
                    'chunk_end_seconds': 2.35,
                },
                headers=auth_headers(token),
            )
        finally:
            app_module.ROLLING_TRANSCRIBE_INTERVAL_MS = original_interval

        assert first.status_code == 200
        assert second.status_code == 200
        first_data = json.loads(first.data)
        second_data = json.loads(second.data)
        assert first_data['text']
        assert second_data['text']
        assert 'world from isweep' not in second_data['text'].lower()
        assert second_data['text'].lower().endswith('now faster')

    def test_captions_transcribe_partial_caption_can_be_corrected_by_stable_caption(self, client):
        import app as app_module
        token, _ = signup_and_get_token(client, email='captions-partial-stable@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base.en'

            def __init__(self):
                self.calls = 0

            def _get_or_create_stt_adapter(self):
                return object()

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                self.calls += 1
                if self.calls == 1:
                    text = 'this caption is partial'
                else:
                    text = 'this caption is partial.'
                return {
                    'status': 'ready',
                    'source': 'audio_stt_live',
                    'events': [],
                    'cleaned_captions': [],
                    'text': text,
                    'clean_text': text,
                    'words': [
                        {'word': 'this', 'start': 1.0, 'end': 1.1},
                        {'word': 'caption', 'start': 1.1, 'end': 1.3},
                        {'word': 'is', 'start': 1.3, 'end': 1.4},
                        {'word': 'partial', 'start': 1.4, 'end': 1.7},
                    ],
                    'failure_reason': None,
                }

        original_interval = app_module.ROLLING_TRANSCRIBE_INTERVAL_MS
        app_module.ROLLING_TRANSCRIBE_INTERVAL_MS = 0
        client.application.analyzer = AnalyzerStub()
        try:
            partial = client.post(
                '/captions/transcribe',
                json={
                    'video_id': 'captions-partial-stable-1',
                    'audio_chunk': make_tone_wav_base64(),
                    'mime_type': 'audio/wav',
                    'chunk_start_seconds': 1.0,
                    'chunk_end_seconds': 2.0,
                },
                headers=auth_headers(token),
            )
            stable = client.post(
                '/captions/transcribe',
                json={
                    'video_id': 'captions-partial-stable-1',
                    'audio_chunk': make_tone_wav_base64(),
                    'mime_type': 'audio/wav',
                    'chunk_start_seconds': 1.2,
                    'chunk_end_seconds': 2.2,
                },
                headers=auth_headers(token),
            )
        finally:
            app_module.ROLLING_TRANSCRIBE_INTERVAL_MS = original_interval

        partial_data = json.loads(partial.data)
        stable_data = json.loads(stable.data)
        assert partial_data['is_partial'] is True
        assert stable_data['is_partial'] is False
        assert stable_data['stable_text'].strip().endswith('.')

    def test_captions_transcribe_populates_latency_diagnostics(self, client):
        token, _ = signup_and_get_token(client, email='captions-latency-diag@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base.en'

            def _get_or_create_stt_adapter(self):
                return object()

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'ready',
                    'source': 'audio_stt_live',
                    'events': [],
                    'cleaned_captions': [],
                    'text': 'latency ready',
                    'clean_text': 'latency ready',
                    'words': [{'word': 'latency', 'start': 2.0, 'end': 2.2}],
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-latency-1',
                'audio_chunk': make_tone_wav_base64(),
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 2.0,
                'chunk_end_seconds': 2.5,
                'capture_started_at': 1000,
                'chunk_started_at': 1100,
                'chunk_flushed_at': 1200,
                'chunk_emitted_at': 1200,
                'backend_received_at': 1210,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data.get('latency'), dict)
        assert data['latency']['capture_started_at'] == 1000
        assert data['latency']['chunk_emitted_at'] == 1200
        assert data['latency']['backend_received_at'] == 1210
        assert isinstance(data['latency']['transcribe_started_at'], int)
        assert isinstance(data['latency']['transcribe_finished_at'], int)
        assert data['latency']['total_latency_ms'] is None or data['latency']['total_latency_ms'] >= 0

    def test_captions_transcribe_accepts_float_audio_payload(self, client):
        token, _ = signup_and_get_token(client, email='captions-transcribe-float-audio@example.com')

        class AnalyzerStub:
            stt_enabled = True
            stt_model_size = 'base'

            def _get_or_create_stt_adapter(self):
                return object()

            def __init__(self):
                self.last_chunk = None
                self.last_mime = None

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                self.last_chunk = audio_chunk
                self.last_mime = mime_type
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [],
                    'cleaned_captions': [],
                    'text': 'hello world',
                    'failure_reason': None,
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-3',
                'sampleRate': 16000,
                'channels': 1,
                'audio': [0.0, 0.1, -0.1, 0.2, -0.2],
                'chunk_start_seconds': 2.0,
                'chunk_end_seconds': 2.2,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['source'] == 'audio_stt_live'
        assert data['text'] == 'hello world'
        assert isinstance(stub.last_chunk, str)
        assert len(stub.last_chunk) > 0
        assert stub.last_mime == 'audio/wav'

    def test_captions_transcribe_always_returns_empty_events(self, client):
        token, _ = signup_and_get_token(client, email='captions-events-empty@example.com')

        class AnalyzerStub:
            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [{'id': 'fake-event', 'start_seconds': 1.0, 'end_seconds': 1.5, 'action': 'mute'}],
                    'cleaned_captions': [],
                    'text': 'hello',
                    'clean_text': 'hello',
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-events',
                'audio_chunk': 'ZmFrZQ==',
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 1.0,
                'chunk_end_seconds': 2.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['events'] == [], 'transcribe must always return events: []'

    def test_captions_transcribe_does_not_return_fallback_profanity_text(self, client):
        import os
        token, _ = signup_and_get_token(client, email='captions-no-fallback@example.com')

        class AnalyzerStub:
            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                from content_analyzer import DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [],
                    'cleaned_captions': [],
                    'text': DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT,
                    'clean_text': DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT,
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()
        response = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-vid-fallback',
                'audio_chunk': 'ZmFrZQ==',
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 0.0,
                'chunk_end_seconds': 2.0,
            },
            headers=auth_headers(token),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['events'] == [], 'events must always be empty from transcribe'

    def test_captions_debug_route_exposes_transcribe_request_counter(self, client):
        token, _ = signup_and_get_token(client, email='captions-debug-route@example.com')

        class AnalyzerStub:
            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [],
                    'cleaned_captions': [],
                    'text': 'hello diagnostics',
                    'clean_text': 'hello diagnostics',
                    'failure_reason': None,
                }

        client.application.analyzer = AnalyzerStub()

        before_resp = client.get('/captions/debug')
        assert before_resp.status_code == 200
        before = json.loads(before_resp.data)
        assert 'transcribe_requests' in before
        before_count = int(before['transcribe_requests'])

        transcribe_resp = client.post(
            '/captions/transcribe',
            json={
                'video_id': 'captions-debug-vid-1',
                'audio_chunk': 'ZmFrZQ==',
                'mime_type': 'audio/wav',
                'chunk_start_seconds': 1.0,
                'chunk_end_seconds': 2.0,
            },
            headers=auth_headers(token),
        )
        assert transcribe_resp.status_code == 200

        after_resp = client.get('/captions/debug')
        assert after_resp.status_code == 200
        after = json.loads(after_resp.data)

        assert after['transcribe_requests'] >= before_count + 1
        assert isinstance(after.get('last_audio_bytes'), int)
        assert isinstance(after.get('last_text_length'), int)

    def test_audio_analyze_uses_chunk_cache_on_second_call(self, client):
        token, _ = signup_and_get_token(client, email='audio-cache@example.com')

        class AnalyzerStub:
            def __init__(self):
                self.calls = 0

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                self.calls += 1
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [{'id': f'audio-{self.calls}', 'start_seconds': 1.0, 'end_seconds': 1.4, 'action': 'mute', 'duration_seconds': 0.4, 'matched_category': 'language', 'reason': 'cached'}],
                    'cleaned_captions': [{'start_seconds': 1.0, 'end_seconds': 1.4, 'text': 'heck', 'clean_text': '____'}],
                    'failure_reason': None,
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub

        first = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-cache-vid', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 1.0, 'end_seconds': 1.5},
            headers=auth_headers(token),
        )
        assert first.status_code == 200
        assert json.loads(first.data)['cached'] is False
        assert stub.calls == 1

        second = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-cache-vid', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 1.0, 'end_seconds': 1.5},
            headers=auth_headers(token),
        )
        assert second.status_code == 200
        second_data = json.loads(second.data)
        assert second_data['cached'] is True
        assert second_data['events'][0]['id'] == 'audio-1'
        assert second_data['clean_captions'] == second_data['cleaned_captions']
        assert stub.calls == 1

    def test_audio_analyze_cache_respects_preferences_fingerprint(self, client):
        token, user_id = signup_and_get_token(client, email='audio-cache-prefs@example.com')

        class AnalyzerStub:
            def __init__(self):
                self.calls = 0

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                self.calls += 1
                duration = preferences.get('categories', {}).get('language', {}).get('duration', 4)
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [{'id': f'audio-prefs-{duration}', 'start_seconds': 2.0, 'end_seconds': 2.4, 'action': 'mute', 'duration_seconds': 0.4, 'matched_category': 'language', 'reason': 'prefs'}],
                    'cleaned_captions': [],
                    'failure_reason': None,
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub

        first = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-prefs-video', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 2.0, 'end_seconds': 2.5},
            headers=auth_headers(token),
        )
        assert first.status_code == 200
        assert json.loads(first.data)['cached'] is False
        assert stub.calls == 1

        db = client.application.database
        prefs = db.get_user_preferences(user_id)
        prefs['categories']['language']['duration'] = 9
        assert db.update_user_preferences(user_id, prefs) is True

        second = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-prefs-video', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 2.0, 'end_seconds': 2.5},
            headers=auth_headers(token),
        )
        assert second.status_code == 200
        second_data = json.loads(second.data)
        assert second_data['cached'] is False
        assert second_data['events'][0]['id'] == 'audio-prefs-9'
        assert stub.calls == 2

    def test_audio_analyze_cache_respects_stt_model(self, client):
        token, _ = signup_and_get_token(client, email='audio-cache-stt@example.com')

        class AnalyzerStub:
            def __init__(self):
                self.calls = 0
                self.stt_model = 'base'

            def get_stt_cache_mode(self):
                return {'enabled': True, 'model': self.stt_model}

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                self.calls += 1
                return {
                    'status': 'ready',
                    'source': 'audio_stt',
                    'events': [{'id': f'audio-stt-{self.stt_model}-{self.calls}', 'start_seconds': 3.0, 'end_seconds': 3.4, 'action': 'mute', 'duration_seconds': 0.4, 'matched_category': 'language', 'reason': 'stt-model'}],
                    'cleaned_captions': [],
                    'failure_reason': None,
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub

        first = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-stt-video', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 3.0, 'end_seconds': 3.5},
            headers=auth_headers(token),
        )
        assert first.status_code == 200
        assert json.loads(first.data)['cached'] is False
        assert stub.calls == 1

        stub.stt_model = 'small'

        second = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-stt-video', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 3.0, 'end_seconds': 3.5},
            headers=auth_headers(token),
        )
        assert second.status_code == 200
        second_data = json.loads(second.data)
        assert second_data['cached'] is False
        assert second_data['events'][0]['id'] == 'audio-stt-small-2'
        assert stub.calls == 2

    def test_audio_analyze_error_results_are_not_cached(self, client):
        token, _ = signup_and_get_token(client, email='audio-cache-error@example.com')

        class AnalyzerStub:
            def __init__(self):
                self.calls = 0

            def analyze_audio_chunk(self, audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id, caption_only=False):
                self.calls += 1
                return {
                    'status': 'error',
                    'source': 'audio_chunk',
                    'events': [],
                    'cleaned_captions': [],
                    'failure_reason': 'analyze_exception',
                }

        stub = AnalyzerStub()
        client.application.analyzer = stub

        first = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-error-video', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 4.0, 'end_seconds': 4.5},
            headers=auth_headers(token),
        )
        assert first.status_code == 200
        first_data = json.loads(first.data)
        assert first_data['status'] == 'error'
        assert first_data['cached'] is False
        assert stub.calls == 1

        second = client.post(
            '/audio/analyze',
            json={'video_id': 'audio-error-video', 'audio_chunk': 'ZmFrZQ==', 'start_seconds': 4.0, 'end_seconds': 4.5},
            headers=auth_headers(token),
        )
        assert second.status_code == 200
        second_data = json.loads(second.data)
        assert second_data['status'] == 'error'
        assert second_data['cached'] is False
        assert stub.calls == 2
