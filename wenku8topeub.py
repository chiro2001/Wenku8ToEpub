import requests
from bs4 import BeautifulSoup as Soup
from ebooklib import epub


class Wenku8ToEpub:
    def __init__(self):
        # api格式
        # 参数1：id千位开头
        # 参数2：id
        self.api = "https://www.wenku8.net/novel/%s/%d/"
        self.api_img = "http://img.wkcdn.com/image/%s/%d/%ds.jpg"
        self.api_page = "https://www.wenku8.net/novel/0/1/2.htm"

    def get_page(self, url_page: str):
        pass

    def get_book(self, id: int, savepath: str=''):
        book = epub.EpubBook()

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
        # print(title, author, url_cover)
        book.set_identifier("%s, %s")
        book.set_title(title)
        book.add_author(author)

        targets = table.select('td')
        for t in targets:
            a = t.select('a')
            # 这是本卷的标题
            text = t.get_text()
            # 排除空白表格
            if len(text) == 1:
                continue
            if len(a) == 0:
                print("Title:", t.get_text(), len(t.get_text()))
                continue
            # 是单章
            a = a[0]
            if a.get_text() == '插图':
                print('Images:', a.get_text())
            else:
                print('Page:', a.get_text())

            url_page = "%s%s" % (self.api % (("%04d" % id)[0], id), a.get('href'))
            print(url_page)


if __name__ == '__main__':
    wk = Wenku8ToEpub()
    wk.get_book(1)