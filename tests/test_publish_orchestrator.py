from pathlib import Path

from social.publish_orchestrator import PublishOrchestrator


class FakeStage:
    def __init__(self): self.cleaned=[]
    def stage(self, path):
        class S: asset_id=44; public_url='https://github.com/o/r/releases/download/gq-media-staging/reel.mp4'
        return S()
    def cleanup(self, asset_id): self.cleaned.append(asset_id)

class FakePipeline:
    def publish(self, **kwargs):
        self.kwargs=kwargs
        class R: media_id='m1'; container_id='c1'
        return R()

class FakeArchive:
    def __init__(self): self.uploaded=[]
    def upload_file(self, file_path, parent_id=None, mime_type=None):
        self.uploaded.append((file_path,parent_id,mime_type)); return {'id':'drive1'}


def test_orchestrator_stages_publishes_archives_and_cleans(tmp_path):
    reel=tmp_path/'reel.mp4'; reel.write_bytes(b'video')
    stage=FakeStage(); pipeline=FakePipeline(); drive=FakeArchive()
    o=PublishOrchestrator(stage=stage, instagram_pipeline=pipeline, drive_store=drive, drive_published_folder_id='folder')
    result=o.publish_reel(topic_id='t1', reel_path=reel, caption='Salut')
    assert pipeline.kwargs['media_url'].startswith('https://github.com/')
    assert result.drive_file_id=='drive1'
    assert stage.cleaned==[44]


def test_orchestrator_cleans_staging_even_if_publish_fails(tmp_path):
    reel=tmp_path/'reel.mp4'; reel.write_bytes(b'video')
    stage=FakeStage()
    class BadPipeline:
        def publish(self, **kwargs): raise RuntimeError('meta failed')
    o=PublishOrchestrator(stage=stage, instagram_pipeline=BadPipeline())
    try:
        o.publish_reel(topic_id='t1', reel_path=reel, caption='Salut')
    except RuntimeError:
        pass
    assert stage.cleaned==[44]
