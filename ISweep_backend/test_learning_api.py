def signup(client, email):
    response = client.post('/auth/signup', json={'email': email, 'password': 'test-password'})
    assert response.status_code in (200, 201)
    data = response.get_json()
    return data['token'], data['user_id']


def headers(token):
    return {'Authorization': f'Bearer {token}'}


def enable_learning(client, token):
    current = client.get('/preferences', headers=headers(token))
    assert current.status_code == 200
    preferences = current.get_json()
    preferences['learning'] = {'enabled': True}
    updated = client.put('/preferences', json=preferences, headers=headers(token))
    assert updated.status_code == 200


def event_payload(dedupe_key='event-1', **overrides):
    payload = {
        'video_id': 'video-abc_1',
        'matched_word': 'hell',
        'caption_source': 'page_caption_dom',
        'timing_method': 'estimated',
        'predicted_start_seconds': 10.0,
        'predicted_end_seconds': 10.4,
        'actual_mute_start_seconds': 10.02,
        'actual_mute_end_seconds': 10.55,
        'playback_speed': 1.0,
        'status': 'restored',
        'playback_context': {'paused': False, 'seeked': False, 'speed_changed': False},
        'dedupe_key': dedupe_key,
    }
    payload.update(overrides)
    return payload


class TestLearningAPI:
    def test_learning_requires_authentication_and_is_disabled_by_default(self, client):
        unauthenticated = client.post('/learning/mute-events', json=event_payload())
        assert unauthenticated.status_code == 401

        token, _ = signup(client, 'learning-disabled@example.com')
        disabled = client.post(
            '/learning/mute-events',
            json={**event_payload(), 'consent': True},
            headers=headers(token),
        )
        assert disabled.status_code == 403

    def test_event_creation_is_account_owned_and_idempotent(self, client):
        token, user_id = signup(client, 'learning-owner@example.com')
        enable_learning(client, token)

        first = client.post(
            '/learning/mute-events', json=event_payload(), headers=headers(token)
        )
        duplicate = client.post(
            '/learning/mute-events', json=event_payload(), headers=headers(token)
        )

        assert first.status_code == 201
        assert first.get_json()['created'] is True
        assert first.get_json()['event']['user_id'] == user_id
        assert duplicate.status_code == 200
        assert duplicate.get_json()['created'] is False
        assert duplicate.get_json()['event']['event_id'] == first.get_json()['event']['event_id']

        listed = client.get('/learning/mute-events?limit=1&offset=0', headers=headers(token))
        assert listed.status_code == 200
        assert listed.get_json()['total'] == 1
        assert len(listed.get_json()['events']) == 1

    def test_event_validation_rejects_bad_timestamps_speed_and_method(self, client):
        token, _ = signup(client, 'learning-validation@example.com')
        enable_learning(client, token)

        for invalid in (
            {'predicted_end_seconds': 10.0},
            {'timing_method': 'muted_by_audio'},
            {'playback_speed': 10.0},
            {'actual_mute_start_seconds': 4.0, 'actual_mute_end_seconds': 3.0},
            {'video_id': '../private'},
        ):
            payload = event_payload(dedupe_key=f"invalid-{len(invalid)}", **invalid)
            response = client.post(
                '/learning/mute-events', json=payload, headers=headers(token)
            )
            assert response.status_code == 400

    def test_feedback_create_update_delete_and_correction_proximity(self, client):
        token, _ = signup(client, 'learning-feedback@example.com')
        enable_learning(client, token)

        first = client.post(
            '/learning/mute-events',
            json=event_payload('first', predicted_start_seconds=10.0, predicted_end_seconds=10.4),
            headers=headers(token),
        )
        first_id = first.get_json()['event']['event_id']
        second = client.post(
            '/learning/mute-events',
            json=event_payload('second', predicted_start_seconds=50.0, predicted_end_seconds=50.4),
            headers=headers(token),
        )
        second_id = second.get_json()['event']['event_id']
        canceled = client.post(
            '/learning/mute-events',
            json=event_payload('canceled', status='canceled', predicted_start_seconds=10.1, predicted_end_seconds=10.5),
            headers=headers(token),
        )
        canceled_id = canceled.get_json()['event']['event_id']

        feedback = client.post(
            f'/learning/mute-events/{first_id}/feedback',
            json={'result': 'late', 'corrected_start_seconds': 10.2, 'corrected_end_seconds': 10.6},
            headers=headers(token),
        )
        assert feedback.status_code == 200
        assert feedback.get_json()['feedback']['result'] == 'late'

        updated = client.put(
            f'/learning/mute-events/{first_id}/feedback',
            json={'result': 'correct', 'corrected_start_seconds': 10.15, 'corrected_end_seconds': 10.52},
            headers=headers(token),
        )
        assert updated.status_code == 200
        assert updated.get_json()['feedback']['result'] == 'correct'

        second_feedback = client.post(
            f'/learning/mute-events/{second_id}/feedback',
            json={'result': 'early', 'corrected_start_seconds': 49.8, 'corrected_end_seconds': 50.2},
            headers=headers(token),
        )
        assert second_feedback.status_code == 200
        canceled_feedback = client.post(
            f'/learning/mute-events/{canceled_id}/feedback',
            json={'result': 'late', 'corrected_start_seconds': 10.2, 'corrected_end_seconds': 10.6},
            headers=headers(token),
        )
        assert canceled_feedback.status_code == 200

        applicable = client.get(
            '/learning/corrections?video_id=video-abc_1&word=HELL&start_seconds=10.05',
            headers=headers(token),
        )
        assert applicable.status_code == 200
        corrections = applicable.get_json()['corrections']
        assert len(corrections) == 2
        assert corrections[0]['event_id'] == first_id
        assert corrections[0]['applicable'] is True
        assert corrections[1]['event_id'] == canceled_id
        assert corrections[1]['successful_mute_example'] is False

        candidates = client.get(
            '/learning/corrections?video_id=video-abc_1&word=hell',
            headers=headers(token),
        )
        assert candidates.status_code == 200
        assert all(item['applicable'] is False for item in candidates.get_json()['corrections'])
        assert {item['event_id'] for item in candidates.get_json()['corrections']} == {first_id, second_id, canceled_id}
        canceled_result = next(item for item in candidates.get_json()['corrections'] if item['event_id'] == canceled_id)
        assert canceled_result['successful_mute_example'] is False

        deleted = client.delete(
            f'/learning/mute-events/{first_id}/feedback', headers=headers(token)
        )
        assert deleted.status_code == 200
        assert client.delete(
            f'/learning/mute-events/{first_id}/feedback', headers=headers(token)
        ).status_code == 404

    def test_feedback_and_corrections_cannot_cross_accounts(self, client):
        owner_token, _ = signup(client, 'learning-owner-two@example.com')
        other_token, _ = signup(client, 'learning-other@example.com')
        enable_learning(client, owner_token)
        enable_learning(client, other_token)
        created = client.post(
            '/learning/mute-events', json=event_payload(), headers=headers(owner_token)
        )
        event_id = created.get_json()['event']['event_id']

        feedback = client.post(
            f'/learning/mute-events/{event_id}/feedback',
            json={'result': 'late', 'corrected_start_seconds': 10.2, 'corrected_end_seconds': 10.6},
            headers=headers(other_token),
        )
        assert feedback.status_code == 404
        listed = client.get('/learning/mute-events', headers=headers(other_token))
        assert listed.status_code == 200
        assert listed.get_json()['total'] == 0
        corrections = client.get(
            '/learning/corrections?video_id=video-abc_1&word=hell&start_seconds=10',
            headers=headers(other_token),
        )
        assert corrections.status_code == 200
        assert corrections.get_json()['corrections'] == []

    def test_learning_cannot_promote_estimated_event_without_feedback(self, client):
        token, _ = signup(client, 'learning-no-promotion@example.com')
        enable_learning(client, token)
        created = client.post(
            '/learning/mute-events', json=event_payload(), headers=headers(token)
        )
        assert created.get_json()['event']['timing_method'] == 'estimated'
        corrections = client.get(
            '/learning/corrections?video_id=video-abc_1&word=hell&start_seconds=10',
            headers=headers(token),
        )
        assert corrections.status_code == 200
        assert corrections.get_json()['corrections'] == []
