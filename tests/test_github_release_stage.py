from pathlib import Path

from storage.github_release_stage import GitHubReleaseStage


class FakeTransport:
    def __init__(self):
        self.get_calls=[]; self.post_json_calls=[]; self.upload_calls=[]; self.delete_calls=[]
        self.release_exists=False
    def get_json(self, url, headers):
        self.get_calls.append((url,headers))
        if not self.release_exists:
            raise FileNotFoundError('not found')
        return {'id':77,'upload_url':'https://uploads.github.com/repos/a/b/releases/77/assets{?name,label}'}
    def post_json(self, url, headers, payload):
        self.post_json_calls.append((url,headers,payload)); self.release_exists=True
        return {'id':77,'upload_url':'https://uploads.github.com/repos/a/b/releases/77/assets{?name,label}'}
    def upload_binary(self, url, headers, file_path, content_type):
        self.upload_calls.append((url,headers,file_path,content_type))
        return {'id':99,'browser_download_url':'https://github.com/a/b/releases/download/gq-media-staging/reel.mp4'}
    def delete(self, url, headers):
        self.delete_calls.append((url,headers)); return None


def test_stage_creates_fixed_release_once_and_uploads_asset(tmp_path):
    video=tmp_path/'reel.mp4'; video.write_bytes(b'video')
    t=FakeTransport()
    stage=GitHubReleaseStage(repository='a/b', token='tok', transport=t)
    staged=stage.stage(video)
    assert staged.asset_id==99
    assert staged.public_url.endswith('/reel.mp4')
    assert t.post_json_calls[0][2]['tag_name']=='gq-media-staging'
    assert 'name=reel.mp4' in t.upload_calls[0][0]


def test_stage_reuses_existing_release(tmp_path):
    video=tmp_path/'reel.mp4'; video.write_bytes(b'video')
    t=FakeTransport(); t.release_exists=True
    stage=GitHubReleaseStage(repository='a/b', token='tok', transport=t)
    stage.stage(video)
    assert t.post_json_calls==[]


def test_cleanup_deletes_only_staged_asset():
    t=FakeTransport(); stage=GitHubReleaseStage(repository='a/b', token='tok', transport=t)
    stage.cleanup(99)
    assert t.delete_calls[0][0]=='https://api.github.com/repos/a/b/releases/assets/99'
