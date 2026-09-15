from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubStageTransport(Protocol):
    def get_json(self, url: str, headers: dict[str, str]) -> dict: ...
    def post_json(self, url: str, headers: dict[str, str], payload: dict) -> dict: ...
    def upload_binary(self, url: str, headers: dict[str, str], file_path: Path, content_type: str) -> dict: ...
    def delete(self, url: str, headers: dict[str, str]) -> None: ...


class UrllibGitHubStageTransport:
    def get_json(self, url, headers):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as r:
                return json.loads(r.read().decode())
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(url) from exc
            raise
    def post_json(self, url, headers, payload):
        req=Request(url,data=json.dumps(payload).encode(),headers={**headers,'Content-Type':'application/json'},method='POST')
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    def upload_binary(self, url, headers, file_path, content_type):
        req=Request(url,data=Path(file_path).read_bytes(),headers={**headers,'Content-Type':content_type},method='POST')
        with urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    def delete(self, url, headers):
        with urlopen(Request(url,headers=headers,method='DELETE'), timeout=30):
            return None


@dataclass(frozen=True)
class StagedAsset:
    asset_id: int
    public_url: str


class GitHubReleaseStage:
    API='https://api.github.com'
    def __init__(self, *, repository: str, token: str, release_tag: str='gq-media-staging', transport: GitHubStageTransport|None=None):
        self.repository=repository.strip(); self.token=token.strip(); self.release_tag=release_tag
        if '/' not in self.repository: raise ValueError('repository must be owner/name')
        if not self.token: raise ValueError('token is required')
        self.transport=transport or UrllibGitHubStageTransport()
    @property
    def headers(self):
        return {'Accept':'application/vnd.github+json','Authorization':f'Bearer {self.token}','X-GitHub-Api-Version':'2026-03-10'}
    def _release(self):
        url=f'{self.API}/repos/{self.repository}/releases/tags/{self.release_tag}'
        try:
            return self.transport.get_json(url,self.headers)
        except FileNotFoundError:
            return self.transport.post_json(
                f'{self.API}/repos/{self.repository}/releases', self.headers,
                {'tag_name':self.release_tag,'name':'GamerQuest temporary media staging','body':'Temporary assets for Instagram publishing.','draft':False,'prerelease':True}
            )
    def stage(self, file_path: str|Path) -> StagedAsset:
        file_path=Path(file_path)
        if not file_path.is_file(): raise FileNotFoundError(file_path)
        release=self._release()
        upload_url=release['upload_url'].split('{',1)[0]
        url=f"{upload_url}?{urlencode({'name':file_path.name})}"
        content_type=mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
        asset=self.transport.upload_binary(url,self.headers,file_path,content_type)
        if not asset.get('id') or not asset.get('browser_download_url'):
            raise RuntimeError('GitHub asset upload returned incomplete response')
        return StagedAsset(int(asset['id']),str(asset['browser_download_url']))
    def cleanup(self, asset_id: int) -> None:
        self.transport.delete(f'{self.API}/repos/{self.repository}/releases/assets/{asset_id}',self.headers)
