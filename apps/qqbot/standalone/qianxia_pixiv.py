import asyncio
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import quote, urlsplit
import unicodedata
import random
import json

import httpx
from PIL import Image
from pydantic import BaseModel

IMAGE_TIMEOUT = 25
MAX_IMAGES = 5

IMAGE_TOOL = {'type':'function','function':{
    'name':'search_images',
    'description':'用户明确要求找图、看插画、壁纸时，搜索 Pixiv 并实际发送图片。不是生成图片。纯询问功能、引用例句或假设讨论时不要调用。',
    'parameters':{'type':'object','properties':{
        'keyword':{'type':'string','minLength':1,'maxLength':80,'description':'要找的角色全名或主题标签'},
        'count':{'type':'integer','minimum':1,'maximum':MAX_IMAGES,'description':'图片张数，未说明时为1'},
    },'required':['keyword','count'],'additionalProperties':False},
}}


@dataclass(frozen=True)
class ImageRequest:
    keyword: str
    count: int = 1

    @classmethod
    def from_tool(cls, raw: str):
        args = json.loads(raw)
        if not isinstance(args, dict) or set(args) - {'keyword','count'}:
            raise ValueError('Invalid image tool arguments')
        keyword,count = args.get('keyword'),args.get('count',1)
        if (not isinstance(keyword,str) or not 1 <= len(keyword.strip()) <= 80
                or type(count) is not int or not 1 <= count <= MAX_IMAGES):
            raise ValueError('Invalid image tool arguments')
        return cls(keyword.strip(),count)


class PixivConfig(BaseModel):
    qianxia_pixiv_enabled: bool = True
    qianxia_pixiv_ai_enabled: bool = True
    qianxia_pixiv_proxy: str = ''
    qianxia_search_proxy: str = ''


class PixivError(Exception):
    pass


@dataclass(frozen=True)
class Artwork:
    id: str
    title: str
    author: str
    image_url: str

    @property
    def url(self):
        return f'https://www.pixiv.net/artworks/{self.id}'


def image_url_ok(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'i.pximg.net'
                and not parsed.username and parsed.port in (None, 443))
    except (ValueError, TypeError):
        return False


def safe_work(row) -> bool:
    return (isinstance(row, dict) and type(row.get('xRestrict')) is int
            and row['xRestrict'] == 0 and type(row.get('illustType')) is int
            and row['illustType'] in (0, 1))


def normal(text: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', text).casefold().split())


def tags_of(row) -> set[str]:
    values = row.get('tags', [])
    if isinstance(values, dict):
        values = values.get('tags', [])
    result = set()
    for item in values if isinstance(values, list) else []:
        if isinstance(item, str):
            result.add(normal(item))
        elif isinstance(item, dict):
            if isinstance(item.get('tag'), str):
                result.add(normal(item['tag']))
            translation = item.get('translation')
            if isinstance(translation, dict):
                result.update(normal(value) for value in translation.values() if isinstance(value, str))
    return result


def relevant_single(row, keyword: str) -> bool:
    if not safe_work(row) or type(row.get('pageCount')) is not int or row['pageCount'] != 1:
        return False
    tags = tags_of(row)
    return normal(keyword) in tags or all(normal(term) in tags for term in keyword.split())


class Pixiv:
    def __init__(self, config: PixivConfig):
        self.config = config
        self.slots = asyncio.Semaphore(2)

    def client(self):
        return httpx.AsyncClient(timeout=12, trust_env=True, follow_redirects=False,
            proxy=self.config.qianxia_pixiv_proxy or self.config.qianxia_search_proxy or None,
            headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.pixiv.net/'})

    async def _json(self, client, url, **kwargs):
        response = await client.get(url, **kwargs)
        response.raise_for_status()
        if len(response.content) > 2 * 1024 * 1024:
            raise PixivError('Pixiv response too large')
        data = response.json()
        if not isinstance(data, dict) or data.get('error') or not isinstance(data.get('body'), dict):
            raise PixivError('Pixiv response unavailable')
        return data['body']

    async def search(self, keyword: str, count: int = 1, *, exclude_ids: set[str] | None = None) -> list[Artwork]:
        if not self.config.qianxia_pixiv_enabled:
            raise PixivError('Pixiv search disabled')
        keyword = keyword.strip()
        if not 1 <= len(keyword) <= 80 or type(count) is not int or not 1 <= count <= MAX_IMAGES:
            raise PixivError('Invalid search arguments')
        results = []
        try:
            async with asyncio.timeout(30), self.slots, self.client() as client:
                seen = set(exclude_ids or ())
                checked = 0
                for page in range(1, 4):
                    body = await self._json(client,
                        'https://www.pixiv.net/ajax/search/illustrations/' + quote(keyword, safe=''),
                        params={'word':keyword, 'order':'date_d', 'mode':'safe', 'p':page,
                                's_mode':'s_tag_full', 'type':'illust', 'lang':'zh'})
                    listing = body.get('illust', {}).get('data', []) if isinstance(body.get('illust'), dict) else []
                    if not isinstance(listing, list):
                        raise PixivError('Invalid search list')
                    candidates = [row for row in listing if relevant_single(row, keyword) and str(row.get('id', '')) not in seen]
                    # Tags cover the entire artwork, not its first page. Single-page
                    # works and explicit titles avoid choosing another character's page.
                    random.shuffle(candidates)
                    candidates.sort(key=lambda row: normal(keyword) not in normal(str(row.get('title', ''))))
                    candidates = candidates[:max(0, 12 - checked)]
                    for row in candidates:
                        pid = str(row.get('id', ''))
                        if not pid.isascii() or not pid.isdecimal() or pid in seen:
                            continue
                        seen.add(pid)
                        checked += 1
                        try:
                            detail = await self._json(client, f'https://www.pixiv.net/ajax/illust/{pid}')
                        except (httpx.HTTPError, PixivError):
                            continue
                        if not relevant_single(detail, keyword) or str(detail.get('illustId', detail.get('id', ''))) != pid:
                            continue
                        urls = detail.get('urls', {})
                        url = urls.get('regular') or urls.get('small') if isinstance(urls, dict) else None
                        title, author = detail.get('illustTitle') or detail.get('title'), detail.get('userName')
                        if not isinstance(title, str) or not isinstance(author, str) or not image_url_ok(url):
                            continue
                        results.append(Artwork(pid, title[:120], author[:80], url))
                        if len(results) == count:
                            return results
                    total = body.get('illust', {}).get('total')
                    if (not listing or checked >= 12 or
                            isinstance(total, int) and page * 60 >= total or
                            not isinstance(total, int) and len(listing) < 60):
                        break
            return results
        except (httpx.HTTPError, ValueError, TypeError, TimeoutError) as exc:
            if results:
                return results
            raise PixivError(type(exc).__name__) from exc

    async def image(self, url: str) -> bytes:
        if not image_url_ok(url):
            raise PixivError('Untrusted image URL')
        try:
            async with asyncio.timeout(IMAGE_TIMEOUT), self.slots, self.client() as client:
                async with client.stream('GET', url) as response:
                    response.raise_for_status()
                    if response.headers.get('content-type', '').split(';')[0] not in {
                        'image/jpeg', 'image/png', 'image/webp', 'image/gif',
                    }:
                        raise PixivError('Image unavailable')
                    limit = 8 * 1024 * 1024
                    if int(response.headers.get('content-length', '0')) > limit:
                        raise PixivError('Image too large')
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > limit:
                            raise PixivError('Image too large')
            with Image.open(BytesIO(data)) as img:
                if img.width * img.height > 36000000:
                    raise PixivError('Image dimensions too large')
                img.verify()
            return bytes(data)
        except (httpx.HTTPError, ValueError, OSError, SyntaxError, TimeoutError, Image.DecompressionBombError) as exc:
            raise PixivError(type(exc).__name__) from exc
