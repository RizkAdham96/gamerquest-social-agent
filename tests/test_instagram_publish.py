from pathlib import Path
import json
import pytest

from social.instagram_publish import InstagramPublisher, ContainerStatusError


class FakeTransport:
    def __init__(self, statuses=None):
        self.posts=[]
        self.gets=[]
        self.statuses=list(statuses or [])
    def post(self, url, params):
        self.posts.append((url, params))
        if url.endswith('/media_publish'):
            return {'id':'ig-media-123'}
        return {'id':'container-123'}
    def get(self, url, params):
        self.gets.append((url, params))
        if self.statuses:
            return self.statuses.pop(0)
        return {'status_code':'FINISHED','status':'ready'}


def make_publisher(transport):
    return InstagramPublisher(
        ig_user_id='ig-user-1',
        access_token='secret-token',
        api_version='v26.0',
        transport=transport,
        sleep_fn=lambda _: None,
    )


def test_create_reel_container_uses_meta_reels_endpoint_and_public_url():
    t=FakeTransport()
    p=make_publisher(t)
    cid=p.create_reel_container('https://cdn.example/reel.mp4','Bonjour',share_to_feed=True)
    assert cid == 'container-123'
    url, params=t.posts[0]
    assert url == 'https://graph.facebook.com/v26.0/ig-user-1/media'
    assert params['media_type']=='REELS'
    assert params['video_url']=='https://cdn.example/reel.mp4'
    assert params['caption']=='Bonjour'
    assert params['share_to_feed']=='true'
    assert params['access_token']=='secret-token'


def test_wait_until_ready_polls_until_finished():
    t=FakeTransport([
        {'status_code':'IN_PROGRESS','status':'processing'},
        {'status_code':'FINISHED','status':'ready'},
    ])
    p=make_publisher(t)
    result=p.wait_until_ready('container-123', max_attempts=3, poll_seconds=0)
    assert result['status_code']=='FINISHED'
    assert len(t.gets)==2


@pytest.mark.parametrize('status_code', ['ERROR','EXPIRED'])
def test_wait_until_ready_fails_for_terminal_container_states(status_code):
    t=FakeTransport([{'status_code':status_code,'status':'bad'}])
    p=make_publisher(t)
    with pytest.raises(ContainerStatusError):
        p.wait_until_ready('container-123', max_attempts=2, poll_seconds=0)


def test_publish_container_calls_media_publish():
    t=FakeTransport()
    p=make_publisher(t)
    media_id=p.publish_container('container-123')
    assert media_id=='ig-media-123'
    url, params=t.posts[0]
    assert url == 'https://graph.facebook.com/v26.0/ig-user-1/media_publish'
    assert params['creation_id']=='container-123'
