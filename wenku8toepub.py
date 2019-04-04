import requests
from bs4 import BeautifulSoup as Soup
from ebooklib import epub
import os
import sys
import getopt


class Wenku8ToEpub:
    def __init__(self):
        # api格式
        # 参数1：id千位开头
        # 参数2：id
        self.api = "https://www.wenku8.net/novel/%s/%d/"
        self.api_img = "http://img.wkcdn.com/image/%s/%d/%ds.jpg"
        self.api_page = "https://www.wenku8.net/novel/0/1/2.htm"

    def get_page(self, url_page: str, title: str=''):
        data = requests.get(url_page).content
        soup = Soup(data, 'html.parser')
        content = soup.select('#content')[0]
        # 去除ul属性
        [s.extract() for s in content("ul")]
        return ("<h1>%s</h1>%s" % (title, content.prettify())).encode()

    def get_book(self, id: int, savepath: str='', fetch_image=True):
        self.book = epub.EpubBook()

        url_cat = "%s%s" % (self.api % (("%04d" % id)[0], id), "index.htm")
        soup_cat = Soup(requests.get(url_cat).content, 'html.parser')
        table = soup_cat.select('table')
        if len(table) == 0:
            print("遇到错误")
            return False
        table = table[0]

        title = soup_cat.select("#title")[0].get_text()
        author = soup_cat.select("#info")[0].get_text().split('作者：')[-1]
        url_cover = self.api_img % (("%04d" % id)[0], id, id)
        data_cover = requests.get(url_cover).content
        # print(title, author, url_cover)
        print('#'*15, '开始下载', '#'*15)
        print('标题:', title, "作者:", author)
        self.book.set_identifier("%s, %s")
        self.book.set_title(title)
        self.book.add_author(author)
        self.book.set_cover('cover.jpg', data_cover)

        # 用于章节排序的文件名
        sumi = 0

        # 目录管理
        toc = []
        # 主线
        spine = ['cover', 'nav']

        targets = table.select('td')
        for t in targets:
            a = t.select('a')
            # 这是本卷的标题
            text = t.get_text()
            # 排除空白表格
            if len(text) == 1:
                continue
            if len(a) == 0:
                volume_text = t.get_text()
                print('volume:', volume_text)
                toc.append((epub.Section(volume_text), []))
                volume = epub.EpubHtml(title=volume_text, file_name='%s.html' % sumi)
                sumi = sumi + 1
                volume.set_content(("<h1>%s</h1><br>" % volume_text).encode())
                self.book.add_item(volume)
                continue
            # 是单章
            a = a[0]

            # 防止没有标题的情况出现
            if len(toc) == 0:
                toc.append((epub.Section(title), []))
            if a.get_text() == '插图':
                print('Images:', a.get_text())
            else:
                print('chapter:', a.get_text())

            title_page = a.get_text()

            url_page = "%s%s" % (self.api % (("%04d" % id)[0], id), a.get('href'))
            data_page = self.get_page(url_page, title=title_page)
            page = epub.EpubHtml(title=title_page, file_name='%s.xhtml' % sumi)
            sumi = sumi + 1

            if fetch_image is True:
                soup_tmp = Soup(data_page, 'html.parser')
                imgcontent = soup_tmp.select(".imagecontent")
                for img in imgcontent:
                    url_img = img.get("src")
                    print('Fetching image:', url_img, '... ', end='')
                    data_img = requests.get(url_img).content
                    filename = url_img.split('http://pic.wkcdn.com/pictures/')[-1]
                    filetype = url_img.split('.')[-1]
                    print('done. filename:', filename, "filetype", filetype)
                    img = epub.EpubItem(file_name="images/%s" % filename, media_type="image/%s" % filetype, content=data_img)
                    self.book.add_item(img)
                    # spine.append(page)

                data_page = (data_page.decode().replace('http://pic.wkcdn.com/pictures/', 'images/')).encode()

            page.set_content(data_page)
            self.book.add_item(page)

            toc[-1][1].append(page)
            spine.append(page)

        self.book.toc = toc

        # add navigation files
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())

        # create spine
        self.book.spine = spine

        epub.write_epub(os.path.join(savepath, '%s - %s.epub' % (title, author)), self.book)


help_str = '''
把www.wenku8.net的轻小说在线转换成epub格式。

wk2epub [-h] [-t] [list]

    list            一个数字列表，中间用空格隔开
    
    -t              Text only.
                    只获取文字，忽略图片。
                    但是图像远程连接仍然保留在文中。
                    此开关默认关闭，即默认获取图片。
                    
    -h              Help.
                    显示本帮助。

调用示例:
    wk2epub -t 1 1213

关于:
    https://github.com/LanceLiang2018/Wenku8ToEpub

版本:
    2019/4/5 2:51 AM
'''


if __name__ == '__main__':
    # wk = Wenku8ToEpub()
    # wk.get_book(2019)
    opts, args = getopt.getopt(sys.argv[1:], '-h-t', [])
    fetch_image = True
    if len(args) == 0:
        print(help_str)
        exit()
    for name, val in opts:
        if '-h' == name:
            print(help_str)
            exit()
        if '-t' == name:
            fetch_image = False

    try:
        args = list(map(int, args))
    except Exception as e:
        print("错误: 参数只接受数字。")
        print(help_str)
        exit()

    for _id in args:
        wk = Wenku8ToEpub()
        wk.get_book(_id, fetch_image=fetch_image)


