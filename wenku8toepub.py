import time

import requests
import bs4
import urllib3
from bs4 import BeautifulSoup as Soup
from ebooklib import epub
import os
import sys
import getopt
from base_logger import get_logger
import threading
import io
import re
import signal
from ebooklib.plugins import ChapterSelector


class Wenku8ToEpub:
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ' \
                 'Chrome/90.0.4430.212 Safari/537.36'

    class BaseError(Exception):
        def __init__(self, data: str = None):
            self.data = data
            logger.error(self.__str__())

        def __str__(self):
            return f"Error: {self.__class__.__name__}{(' : %s' % self.data) if self.data is not None else ''}"

    class ArgsError(BaseError):
        pass

    class Watcher:
        # 当 Ctrl + C 结束程序，保存当前进度
        instance = None

        def __init__(self, on_exit, args: list = None, kwargs: dict = None):
            if on_exit is None:
                return
            self.args: list = args
            if self.args is None:
                self.args = []
            self.kwargs: list = kwargs
            if self.kwargs is None:
                self.kwargs = {}
            self.on_exit = on_exit
            Wenku8ToEpub.Watcher.instance = self

        def start_watch(self):
            signal.signal(signal.SIGINT, self.watch)

        @staticmethod
        def watch(*args, **kwargs):
            self = Wenku8ToEpub.Watcher.instance
            self.on_exit(*self.args, **self.kwargs)

    def __init__(self,
                 username: str = 'wenku8toepub',
                 password: str = 'wenku8toepub',
                 proxy: str = None, **kwargs):
        # api格式
        # 参数1：id千位开头
        # 参数2：id
        self.api = "https://www.wenku8.net/novel/%s/%d/"
        self.api_info = "https://www.wenku8.net/book/%d.htm"
        # self.api_img = "http://img.wkcdn.com/image/%s/%d/%ds.jpg"
        self.api_img = "https://img.wenku8.com/image/%s/%d/%ds.jpg"
        self.img_splits = ['http://pic.wenku8.com/pictures/',
                           'http://pic.wkcdn.com/pictures/',
                           'http://picture.wenku8.com/pictures/',
                           'https://pic.wenku8.com/pictures/',
                           'https://pic.wkcdn.com/pictures/',
                           'https://picture.wenku8.com/pictures/']
        self.api_login = 'http://www.wenku8.net/login.php?do=submit"'
        self.api_search_1 = 'http://www.wenku8.net/modules/article/search.php?searchtype=articlename&searchkey=%s'
        self.api_search_2 = 'http://www.wenku8.net/modules/article/search.php?searchtype=author&searchkey=%s'
        self.api_txt = 'http://dl.wenku8.com/down.php?type=txt&id=%d'
        self.cookies = ''
        self.cookie_jar = None
        self.book = epub.EpubBook()
        self.thread_img_pool = []
        self.thread_pool = []
        # 用于章节排序的文件名
        self.sum_index = 0
        # 目录管理
        self.toc = []
        # 主线
        self.spine = ['cover', 'nav']
        # 当前章节
        self.chapters = []
        self.book_id: int = 0
        self.image_size = None
        self.image_count = 0

        self.proxy: str = proxy

        self.lock = threading.Lock()

        self.logger = kwargs.get('logger', None)
        if self.logger is None:
            self.logger = get_logger(__name__)

        # 搜索用账号
        self.username, self.password = username, password

        # 解决结束程序的进度保存问题
        self.running: bool = False
        self.watcher = Wenku8ToEpub.Watcher(on_exit=self.on_exit)

        # 是否使用原书名做文件名
        self.raw_book_name: bool = kwargs.get('raw_book_name', False)

    def on_exit(self):
        logger.warning(f"Exiting and saving file...")
        self.lock.acquire()
        self.running = False
        self.lock.release()

    def get_proxy(self) -> dict:
        if self.proxy is None:
            return {}
        return {
            'http': self.proxy,
            'https': self.proxy
        }

    # 登录，能够使用搜索功能。
    def login(self, username: str = None, password: str = None):
        username = self.username if username is None else username
        password = self.password if password is None else password
        if username is None or password is None:
            raise Wenku8ToEpub.ArgsError()
        payload = {'action': 'login',
                   'jumpurl': '',
                   'username': username,
                   'password': password}
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': Wenku8ToEpub.USER_AGENT
        }
        response = requests.request("POST", self.api_login, headers=headers, data=payload, proxies=self.get_proxy())
        html = response.content.decode('gbk')
        if '登录成功' not in html:
            self.logger.error("登录失败")
            return
        cookie_value = ''
        for key, value in response.cookies.items():
            cookie_value += key + '=' + value + ';'
        self.cookies = cookie_value
        self.cookie_jar = response.cookies

    # 搜索，应该先登录
    def search(self, key: str):
        books = self.search_one(self.api_search_1, key)
        books.extend(self.search_one(self.api_search_2, key))
        return books

    def search_one(self, selected_api: str, key: str):
        self.login()
        if len(self.cookies) == 0 or self.cookie_jar is None:
            # 还没有登录
            self.logger.error("请先登录再使用搜索功能")
            return []
        headers = {
            'User-Agent': Wenku8ToEpub.USER_AGENT,
            'Content-Type': 'multipart/form-data; boundary=--------------------------607040101744888865545920',
            'Cookie': self.cookies
        }
        # 注意编码问题
        # 云 -> %D4%C6
        encodings = key.encode('gbk').hex().upper()
        key_arg = ''
        for i in range(0, len(encodings), 2):
            key_arg = key_arg + '%' + encodings[i] + encodings[i + 1]
        response = requests.request("GET", selected_api % key_arg, headers=headers, cookies=self.cookie_jar,
                                    proxies=self.get_proxy())
        html = response.content.decode("gbk", errors='ignore')
        soup = Soup(html, 'html.parser')

        if '推一下' in html:
            # 直接进入了单本状态
            # print(soup)
            # print(title, bid, cover, status, brief)
            title = soup.find_all('b')[1].get_text()
            bid = ''
            for n in re.findall('\d', response.url)[1:]:
                bid = bid + n
            bid = int(bid)
            try:
                cover = soup.find_all('img')[1].get_attribute_list('src')[0]
            except IndexError:
                cover = None
            try:
                status = soup.find_all('table')[0].find_all('tr')[2].get_text().replace('\n', ' ')
            except IndexError:
                status = None
            brief = '(Missing...)'
            try:
                brief = soup.find_all('table')[2].find_all('td')[1].find_all('span')[4].get_text()
            except IndexError:
                spans = soup.find_all('span')
                for i in range(len(spans)):
                    if '内容简介' in spans[i].get_text():
                        brief = spans[i + 1].get_text()
            book = {
                'title': title, 'bid': bid, 'cover': cover, 'status': status, 'brief': brief
            }
            return [book, ]

        td = soup.find('td')
        books = []
        for content in td.children:
            if not isinstance(content, bs4.element.Tag):
                continue
            title = content.find_all('a')[1].get_text()
            url = content.find_all('a')[1].get_attribute_list('href')[0]
            numbers = re.findall('\d', url)[1:]
            bid = ''
            for n in numbers:
                bid = bid + n
            bid = int(bid)
            cover = content.find_all('img')[0].get_attribute_list('src')[0]
            status = content.find_all('p')[0].get_text()
            brief = content.find_all('p')[1].get_text()[3:]
            book = {
                'title': title, 'bid': bid, 'cover': cover, 'status': status, 'brief': brief
            }
            books.append(book)

        return books

    # 获取书籍信息。
    # {
    #   id, name, author, brief, cover, copyright
    # }
    def book_info(self, book_id: int):
        url_cat = "%s%s" % (self.api % (("%04d" % book_id)[0], book_id), "index.htm")
        resp = requests.get(url_cat, headers={'User-Agent': Wenku8ToEpub.USER_AGENT}, proxies=self.get_proxy()).content
        soup_cat = Soup(resp, 'html.parser')
        table = soup_cat.select('table')
        if len(table) == 0:
            self.logger.error("遇到错误")
            return None
        table = table[0]

        if len(soup_cat.select("#title")) == 0:
            self.logger.error('该小说不存在！id = ' + str(book_id))
            return None
        title = soup_cat.select("#title")[0].get_text()
        author = soup_cat.select("#info")[0].get_text().split('作者：')[-1]
        url_cover = self.api_img % (("%04d" % book_id)[0], book_id, book_id)

        brief = ''
        url_cat2 = self.api_info % (book_id,)
        soup_cat2 = Soup(
            requests.get(url_cat2, headers={'User-Agent': Wenku8ToEpub.USER_AGENT}, proxies=self.get_proxy()).content,
            'html.parser')
        update = ''
        for td in soup_cat2.find_all('td'):
            if '最后更新' in td.get_text():
                update = td.get_text()[5:]
        is_copyright = True
        if '因版权问题，文库不再提供该小说的在线阅读与下载服务！' in soup_cat2.get_text():
            is_copyright = False
        spans = soup_cat2.select('span')
        for i in range(len(spans)):
            span = spans[i]
            if '内容简介' in span.get_text():
                brief = spans[i + 1].get_text()
        return {
            "id": book_id,
            "name": title,
            "author": author,
            "brief": brief,
            "cover": url_cover,
            'copyright': is_copyright,
            'update': update
        }

    # 获取版权状态
    def copyright(self, book_id=None):
        if book_id is None:
            book_id = self.book_id
        data = requests.get(self.api_info % book_id, headers={'User-Agent': Wenku8ToEpub.USER_AGENT},
                            proxies=self.get_proxy()).content
        soup = Soup(data, 'html.parser')
        if '因版权问题，文库不再提供该小说的在线阅读与下载服务！' in soup.get_text():
            return False
        return True

    def id2name(self, book_id: int):
        url_cat = "%s%s" % (self.api % (("%04d" % book_id)[0], book_id), "index.htm")
        soup_cat = Soup(
            requests.get(url_cat, header={'User-Agent': Wenku8ToEpub.USER_AGENT}, proxies=self.get_proxy()).content,
            'html.parser')
        table = soup_cat.select('table')
        if len(table) == 0:
            self.logger.error("遇到错误")
            return ''
        table = table[0]

        if len(soup_cat.select("#title")) == 0:
            self.logger.error('该小说不存在！id = ' + str(book_id))
            return ''
        title = soup_cat.select("#title")[0].get_text()
        # author = soup_cat.select("#info")[0].get_text().split('作者：')[-1]
        # url_cover = self.api_img % (("%04d" % self.book_id)[0], self.book_id, self.book_id)
        return title

    def get_page(self, url_page: str, title: str = ''):
        _res_code = -1
        _res = None
        while _res_code != 200:
            try:
                _res = requests.get(url_page, headers={'User-Agent': Wenku8ToEpub.USER_AGENT}, proxies=self.get_proxy(), timeout=30)
            except requests.exceptions.Timeout:
                time.sleep(5)
                continue
            except requests.exceptions.ConnectionError:
                time.sleep(5)
                continue
            except urllib3.exceptions.ReadTimeoutError:
                time.sleep(5)
                continue
            _res_code = _res.status_code

        data = _res.content
        soup = Soup(data, 'html.parser')
        content = soup.select('#content')[0]
        # 去除ul属性
        [s.extract() for s in content("ul")]
        return ("<h1>%s</h1>%s" % (title, content.prettify())).encode()

    def fetch_img(self, url_img):
        if self.image_size is not None and self.image_size < self.image_count:
            self.logger.warn('达到最大图像总计大小，取消图像下载')
            # 此时文档中的链接是错误的...所以贪心要付出代价
            # 上一行注释是啥来着(?)
            return
        if not self.running:
            logger.warning(f'Canceling image: {url_img}')
            return
        self.logger.info('->Fetching image: ' + url_img + '...')
        data_img = requests.get(url_img, headers={'User-Agent': Wenku8ToEpub.USER_AGENT},
                                proxies=self.get_proxy()).content
        self.image_count = self.image_count + len(data_img)
        filename = None
        for sp in self.img_splits:
            if sp in url_img:
                filename = url_img.split(sp)[-1]
        if filename is None:
            filename = url_img.split(':')[-1].split('//')[-1]
        filetype = url_img.split('.')[-1]
        # print('done. filename:', filename, "filetype", filetype)
        img = epub.EpubItem(file_name="images/%s" % filename,
                            media_type="image/%s" % filetype, content=data_img)
        self.lock.acquire()
        self.book.add_item(img)
        self.lock.release()
        self.logger.info('<-Done image: ' + url_img)

    def fetch_chapter(self, a, order: int, fetch_image: bool):
        if a.get_text() == '插图':
            self.logger.info('Images: ' + a.get_text())
        else:
            self.logger.info('Chapter: ' + a.get_text())

        title_page = a.get_text()

        url_page = "%s%s" % (self.api % (("%04d" % self.book_id)[0], self.book_id), a.get('href'))

        if not self.running:
            logger.warning(f'Canceling chapter: {url_page}')
            return

        data_page = self.get_page(url_page, title=title_page)
        self.lock.acquire()
        page = epub.EpubHtml(title=title_page, file_name='%s.xhtml' % self.sum_index)
        # 多线程模式下文件名会不按照顺序...
        self.sum_index = self.sum_index + 1
        self.lock.release()

        if fetch_image is True:
            soup_tmp = Soup(data_page, 'html.parser')
            img_content = soup_tmp.select(".imagecontent")
            self.thread_img_pool = []
            for img in img_content:
                url_img = img.get("src")
                # 排除其他站点的图片，防止访问超时
                origin = False
                for wenku8_img in self.img_splits:
                    if wenku8_img in url_img:
                        origin = True
                if not origin:
                    continue
                th = threading.Thread(target=self.fetch_img, args=(url_img,))
                self.thread_img_pool.append(th)
                th.setDaemon(True)
                th.start()

            for it in self.thread_img_pool:
                it.join()

            # 在应该下载图片的时候进行替换
            if self.image_size is None \
                    or (self.image_size is not None and self.image_size > self.image_count):
                for url in self.img_splits:
                    data_page = (data_page.decode().replace(url, 'images/')).encode()

        page.set_content(data_page)
        self.lock.acquire()
        self.book.add_item(page)
        self.lock.release()

        self.chapters[order] = page

    def get_book_no_copyright(self, targets, author: str = 'undefined', **kwargs):
        response = requests.get(self.api_txt % self.book_id, stream=True,
                                headers={'User-Agent': Wenku8ToEpub.USER_AGENT}, proxies=self.get_proxy())
        chunk_size = 1024 * 100  # 单次请求最大值
        content_size = 0  # 内容体总大小
        self.logger.info('该书没有版权，开始下载TXT文件转化为EPUB')
        data_download = io.BytesIO()
        for data in response.iter_content(chunk_size=chunk_size):
            data_download.write(data)
            content_size = int(content_size + len(data))
            self.logger.info('已经下载 %s KB' % (content_size // 1024))
        data_download.seek(0)
        txt = data_download.read().decode('gbk', errors='ignore')
        self.logger.info('TXT下载完成')
        title = re.findall('<.+>', txt[:81])[0][1:-1]
        txt = txt[40 + len(title):-76]

        volumes = []
        chapters = []
        for tar in targets:
            if tar.get_attribute_list('class')[0] == 'vcss':
                volumes.append(tar.get_text())
                chapters.append({
                    'volume': tar.get_text(),
                    'chapters': []
                })
                continue
            if tar.get_attribute_list('class')[0] == 'ccss' \
                    and tar.get_text().encode() != b'\xc2\xa0':
                chapters[-1]['chapters'].append(tar.get_text())
                continue

        last_end = 0
        length = len(txt)
        for i in range(len(chapters)):
            v = chapters[i]
            txt_all = []
            volume_text = v['volume']
            self.logger.info('volume: ' + volume_text)
            for c in v['chapters']:
                anchor = "%s %s" % (volume_text, c)
                next_end = txt.find(anchor, last_end, length)
                # print('next_end', next_end)
                if next_end <= 6:
                    continue
                txt_slice = txt[last_end: next_end]
                last_end = next_end
                txt2 = ''
                for line in txt_slice.splitlines():
                    txt2 = txt2 + '<p>%s</p>' % line
                txt_slice = txt2
                txt_all.append(txt_slice)
            if i + 1 == len(chapters):
                txt_all.append(txt[last_end:])
            else:
                point = txt.find(chapters[i + 1]['volume'], last_end, length)
                # print('point', point)
                txt_all.append(txt[last_end:point])
                last_end = point - 1

            if len(txt_all) != len(v['chapters']):
                # print('err')
                # 虽然不知道为啥，这么写就对了
                txt_all = txt_all[1:]

            # 先增加卷
            self.toc.append((epub.Section(volume_text), []))
            self.lock.acquire()
            volume = epub.EpubHtml(title=volume_text, file_name='%s.html' % self.sum_index)
            self.sum_index = self.sum_index + 1
            volume.set_content(("<h1>%s</h1><br>" % volume_text).encode())
            self.book.add_item(volume)
            self.lock.release()

            # 增加章节
            for i in range(len(v['chapters'])):
                chapter_title = v['chapters'][i]
                self.logger.info('chapter: ' + chapter_title)
                self.lock.acquire()
                page = epub.EpubHtml(title=chapter_title, file_name='%s.xhtml' % self.sum_index)
                self.sum_index = self.sum_index + 1
                self.lock.release()
                # warn issue #7
                try:
                    text_content = txt_all[i]
                except IndexError:
                    logger.error(f"文本文件解析出错，本卷可能无法对齐标题与内容")
                    continue
                # fix issue #5: lxml.etree.ParserError: Document is empty
                if len(text_content) == 0:
                    continue
                # logger.info(f"text_content: {text_content[:20]}... ({len(text_content)})")
                page.set_content(text_content)
                self.lock.acquire()
                self.book.add_item(page)
                self.lock.release()
                self.toc[-1][1].append(page)
                self.spine.append(page)

        self.save_book(title, author, **kwargs)

    def get_book(self, book_id: int,
                 fetch_image: bool = True,
                 image_size=None, **kwargs):
        # :param image_size 图像总计最大大小（字节数）
        self.image_size = image_size
        self.book_id = book_id

        url_cat = "%s%s" % (self.api % (("%04d" % self.book_id)[0], self.book_id), "index.htm")
        soup_cat = Soup(
            requests.get(url_cat, headers={'User-Agent': Wenku8ToEpub.USER_AGENT}, proxies=self.get_proxy()).content,
            'html.parser')
        table = soup_cat.select('table')
        if len(table) == 0:
            self.logger.error("遇到错误")
            return False
        table = table[0]

        if len(soup_cat.select("#title")) == 0:
            self.logger.error('该小说不存在！id = ' + str(self.book_id))
            return
        title = soup_cat.select("#title")[0].get_text()
        author = soup_cat.select("#info")[0].get_text().split('作者：')[-1]
        url_cover = self.api_img % (("%04d" % self.book_id)[0], self.book_id, self.book_id)
        data_cover = requests.get(url_cover, headers={'User-Agent': Wenku8ToEpub.USER_AGENT},
                                  proxies=self.get_proxy()).content
        self.logger.info('#' * 15 + '开始下载' + '#' * 15)
        self.logger.info('标题: ' + title + " 作者: " + author)
        self.book.set_identifier("%s, %s" % (title, author))
        self.book.set_title(title)
        self.book.set_language('zh')
        self.book.add_author(author)
        self.book.set_cover('cover.jpg', data_cover)

        self.running = True
        self.watcher.start_watch()

        targets = table.select('td')
        is_copyright = self.copyright()
        if not is_copyright:
            # if is_copyright:
            # 没有版权的时候
            return self.get_book_no_copyright(targets, bin_mode=kwargs.get('bin_mode', False), author=author)

        order = 0
        chapter_names = []
        time.sleep(2)  # 为了减少cloudflare错误逻辑，在这里暂停2秒
        '''
        在这里添加单章逻辑
        书名也要改成标题 + 第x章
        使用装饰器实现，不改变原先的逻辑
        '''
        @ChapterSelector.chapterselector(_chapter_select_mode, self.logger.info)
        def getBooks(targets):
            for tar in targets:
                a = tar.select('a')
                # 这是本卷的标题
                text = tar.get_text()
                # 排除空白表格

                if len(self.thread_pool) >= 4:
                    time.sleep(10)  # 当线程大于时休眠
                    for thread in self.thread_pool:
                        thread.join()  # 保证所有线程结束任务
                    self.thread_pool.clear() # 清空即可


                if text.encode() == b'\xc2\xa0':
                    # print('排除了', text, text.encode() == b'\xc2\xa0')
                    continue
                if len(a) == 0:
                    volume_text = tar.get_text()
                    self.logger.info('volume: ' + volume_text)

                    # 上一章节的chapter
                    for th in self.thread_pool:
                        th.join()
                    # 已经全部结束
                    if len(self.thread_pool) != 0:
                        self.thread_pool = []
                        for chapter in self.chapters:
                            if chapter is None:
                                continue
                            self.toc[-1][1].append(chapter)
                            self.spine.append(chapter)

                    self.chapters = [None for _ in range(len(targets))]
                    order = 0
                    self.toc.append((epub.Section(volume_text), []))
                    self.lock.acquire()
                    volume = epub.EpubHtml(title=volume_text, file_name='%s.html' % self.sum_index)
                    self.sum_index = self.sum_index + 1
                    volume.set_content(("<h1>%s</h1><br>" % volume_text).encode())
                    self.book.add_item(volume)
                    self.lock.release()
                    continue
                # 是单章
                a = a[0]

                """
                在这里由于cloudflare防攻击配置，访问得过快会导致access deny, 所以这里要调整线程数量
                """
                th = threading.Thread(target=self.fetch_chapter, args=(a, order, fetch_image))
                chapter_names.append(a.get_text())
                order = order + 1
                self.thread_pool.append(th)
                th.setDaemon(True)
                th.start()
                time.sleep(0.5)
        getBooks(targets)
        # 最后一个章节的chapter
        for th in self.thread_pool:
            th.join()
        # 已经全部结束
        if len(self.thread_pool) != 0:
            self.thread_pool = []
            for chapter in self.chapters:
                if chapter is None:
                    continue
                self.toc[-1][1].append(chapter)
                self.spine.append(chapter)

        self.save_book(title, author, **kwargs)

    def save_book(self, title: str, author: str, bin_mode: bool = False, save_path: str = '', index: int = None):
        # fix issue #8
        def remove_special_symbols(s: str, refill: str = '_') -> str:
            symbols = """"';:<>./\\+`~!@#$%^&*"""
            for symbol in symbols:
                s = s.replace(symbol, refill)
            return s

        # noinspection PyStringFormat
        @ChapterSelector.changeToChapterBookName(flag=_chapter_select_mode,
                                                 title=title,
                                                 author=author,
                                                 remove_special_symbols=remove_special_symbols,
                                                 index=index,
                                                 raw_book_name=self.raw_book_name)
        def generate_filename(index_: int):
            return '%s - %s%s.epub' % (
                *[remove_special_symbols(s) if not self.raw_book_name else s for s in [title, author]],
                '' if index is None else f'({index_})')

        if bin_mode is True:
            stream = io.BytesIO()
            epub.write_epub(stream, self.book)
            stream.seek(0)
            return stream.read()
        if index is None:
            self.book.toc = self.toc
            # 添加目录信息
            self.book.add_item(epub.EpubNcx())
            self.book.add_item(epub.EpubNav())
            # 创建主线，即从头到尾的阅读顺序
            self.book.spine = self.spine

        path = os.path.join(save_path, generate_filename(index_=index))
        if os.path.exists(path):
            if index is None:
                logger.warning(f"{path} exists, saving to another file...")
            self.save_book(title, author, bin_mode=bin_mode, save_path=save_path,
                           index=(index + 1 if index is not None else 1))
        else:
            epub.write_epub(path, self.book)
            logger.warning(f"saved to {generate_filename(index_=index)}")


help_str = '''
把 www.wenku8.net 的轻小说在线转换成epub格式。
wenku8.net 没有版权的小说则下载 TXT 文件然后转换为 epub 文件。

wk2epub [-h] [-t] [-m] [-b] [-c] [-s search_word] [-p proxy_url] [list]

    list            一个数字列表，表示 wenku8 的书的ID（从链接可以找到）。
                    中间用空格隔开。此项请放在最后。
    -t              只获取文字，忽略图片，但是图像远程链接仍然保留在文中。
                    此开关默认关闭，即默认获取图片。
    -i              显示该书信息。
    -s search_key   按照关键词搜索书籍。
    -p proxy_url    使用代理。(*_proxy等环境变量同样有效。)
    -b              把生成的epub文件直接从标准输出返回。此时list长度应为1。
    -h              显示本帮助。
    -r              不剔除特殊符号而使用原书名作为文件名保存。
    -c              指定下载的章节范围
    
    Example:        wk2epub -t 2541
    About:          https://github.com/chiro2001/Wenku8ToEpub
    Version:        2021/12/03 10:53 AM
'''

logger = get_logger()

if __name__ == '__main__':
    try:
        _opts, _args = getopt.getopt(sys.argv[1:], '-c-h-t-b-i-r-os:p:', [])
    except getopt.GetoptError as e:
        logger.error(f'参数解析错误: {e}')
        sys.exit(1)
    _fetch_image = True
    _bin_mode = False
    _show_info = False
    _print_help = True
    _run_mode = 'download'
    _search_key: str = None
    _proxy: str = None
    _raw_book_name: bool = False
    _chapter_select_mode: bool = False
    for name, val in _opts:
        if '-h' == name:
            print(help_str)
            sys.exit()
        if '-t' == name:
            _fetch_image = False
        if '-b' == name:
            _bin_mode = True
        if '-i' == name:
            _show_info = True
        if '-s' == name:
            _run_mode = 'search'
            _search_key = val
        if '-p' == name:
            _proxy = val
            logger.warning(f'using proxy: {_proxy}')
        if '-r' == name:
            _raw_book_name = True
        if '-c' == name:
            _chapter_select_mode = True
    if _run_mode == 'search':
        wk = Wenku8ToEpub(proxy=_proxy)
        _books = wk.search(_search_key)
        for _book in _books:
            logger.info(f"ID:{_book['bid']:4} {_book['title']:8} "
                        f"{(_book['status'][:18] + '...') if len(_book['status']) >= 21 else _book['status']}")
    else:
        if len(_args) == 0:
            print(help_str)
            sys.exit()
        try:
            _args = list(map(int, _args))
        except ValueError as e:
            logger.error("错误: 参数只接受数字。")
            logger.error(f"args: {_args}")
            print(help_str)
            sys.exit()
        for _id in _args:
            wk = Wenku8ToEpub(logger=logger, proxy=_proxy, raw_book_name=_raw_book_name)
            _book_info = wk.book_info(_id)
            # fix issue #6: UnicodeEncodeError: 'gbk' codec can't encode character
            # (But I didn't reproduce the bug.)
            try:
                print('信息：ID:%s\t书名:%s\t作者:%s' % (_book_info['id'], _book_info['name'], _book_info['author']))
                print('简介：\n%s' % _book_info['brief'])
            except Exception as e:
                logger.error(f"error when reading info: {e.__class__.__name__} {e}")
            res = wk.get_book(_id, fetch_image=_fetch_image, bin_mode=_bin_mode)
            if _bin_mode is True:
                print(res)
