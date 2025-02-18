import json
import os
from os import path
from pathlib import PurePosixPath
from urllib.parse import urlparse

from itemadapter import ItemAdapter
from scrapy import Request
from scrapy.pipelines.files import FilesPipeline

from steam_scraping.db import db


class MyFilesPipeline(FilesPipeline):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = db
        self.STORE_URI = args[0]
        self.test_mode = None

    def open_spider(self, spider):
        self.test_mode = spider.test_mode
        super().open_spider(spider)

    def file_path(self, request, response=None, info=None, *, item=None):
        adapter = ItemAdapter(item)
        return f'{adapter["app_id"]}/{PurePosixPath(urlparse(request.url).path).name}'

    def get_media_requests(self, item, info):
        adapter = ItemAdapter(item)
        file_urls = adapter.get('file_urls')

        if file_urls is None:
            return

        for file_url in file_urls:
            yield Request(file_url, meta={'is_resource': True})

    def item_completed(self, results, item, info):
        adapter = ItemAdapter(item)
        all_ok = all([result[0] for result in results])
        if all_ok and self.test_mode is None:
            self.db.update_by_id(adapter['db_id'], {'status': 'complete'})

        images_path = []
        videos_path = []
        for ok, info_or_failure in results:
            if not ok:
                continue

            file_path = info_or_failure['path']
            is_mp4 = file_path.endswith('.mp4')
            file_path = path.normpath(path.join(self.STORE_URI, file_path))

            if is_mp4:
                videos_path.append(file_path)
                continue
            images_path.append(file_path)

        adapter['images_path'] = images_path
        adapter['videos_path'] = videos_path

        return item


class SetDefaultPipeline:
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)

        for key in item.fields:
            adapter.setdefault(key, None)

        return item


class SaveItemAsJSONPipeline:
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.FILES_STORE = settings.get('FILES_STORE')

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        app_id = adapter['app_id']
        app_path = path.join(self.FILES_STORE, str(app_id))
        os.makedirs(app_path, exist_ok=True)

        json_path = path.join(app_path, f'data.json')
        with open(json_path, 'w', encoding='utf-8') as fh:
            json.dump(adapter.asdict(), fh)

        return item
