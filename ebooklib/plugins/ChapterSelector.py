# @Time    : 2024/8/15 14:35
# @Author  : TwoOnefour
# @blog    : https://www.pursuecode.cn
# @Email   : twoonefour@pursuecode.cn
# @File    : ChapterSelector.py
import sys
from functools import wraps
from bs4 import BeautifulSoup


class LinkedTitleNode:
    """
    用于标题存储的链表节点
    """
    def __init__(self, index=None, pre=None, nxt=None, title=None):
        self.index = index
        self.pre = pre
        self.next = nxt
        self.title = title


title_map = {'head': LinkedTitleNode(), 'tail': LinkedTitleNode()}  # 哈希用于快速找到节点

chapterArray = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]  # 用于映射中文
Start_Chapter_index = 0
End_Chapter_index = 0  # 用于多章节下载时指定书名
def chapterselector(flag, loggerFunc):
    """
    装饰器。改变下载章节方法的行为。
    重构：在这里输出序号让用户选择，这样就可以解决非整数章节的问题
    :param flag: 判断是否生效的标志
    :param loggerFunc: 传入日志方法用于格式化标准输出
    :return: 被修饰的新方法
    """
    def wrapper(func):
        @wraps(func)
        def changetargets(*args, **kwargs):
            start_index: int = 0
            findFlag: bool = False
            end_index: int = len(args[0])
            tmp_res: str = None

            nowNode = title_map['head']
            title_map['head'].next = title_map['tail']
            title_map['tail'].pre = title_map['head']
            title_map['head'].index = 0
            title_map['tail'].index = len(args[0])
            title_map[len(args[0])] = title_map['tail']
            title_map[0] = title_map['head']
            for index, tag in enumerate(args[0]):
                if tag.has_key("colspan"):  # 如果是章节名字
                    tmpNode = LinkedTitleNode(title=tag.text, index=index, nxt=title_map["tail"], pre=nowNode)
                    title_map["tail"].pre = tmpNode
                    nowNode.next = tmpNode
                    nowNode = tmpNode
                    loggerFunc(f"[{index}] {tag.text}")
                    title_map[index] = tmpNode

            loggerFunc(f"请输入章节前的序号以序号开始的章节")

            while True:
                try:
                    index = int(input())
                    if index not in title_map:
                        raise ValueError

                    # findFlag = True
                    start_index = index

                    break
                except Exception as e:
                    loggerFunc("输入错误或不存在，请输入章节前的序号以选择章节")

            if title_map[start_index].next != title_map['tail']:
                # 如果下一个标题为空则直接跳过选择（最新一章就不用考虑后面的章节了）
                while True:
                    loggerFunc("是否需要下载该章节之后的所有章节, 请输入是或否，默认（是）")
                    tmp_res = input()
                    if tmp_res == "":
                        tmp_res = "是"
                        break
                    if tmp_res in {"是", "否"}:
                        break
                if tmp_res == "否":
                    while True:
                        try:
                            loggerFunc("输入章节前的序号, 如开始章节为24，停止章节为25，则只会下载24，同理停止章节为26，则会下载24-25")
                            end_index = int(input())
                            assert end_index > start_index
                            if end_index not in title_map:
                                raise ValueError
                            break
                        except Exception as e:
                            loggerFunc("输入错误或不存在，请输入章节前的序号以选择章节, 或者输入的数字比开始章节小")
                else:
                    end_index = title_map["tail"].index

            global End_Chapter_index
            global Start_Chapter_index
            End_Chapter_index = end_index
            Start_Chapter_index = start_index
            return func((args[0][start_index:end_index]))
        return changetargets if flag else func
    return wrapper


def changeToChapterBookName(flag, remove_special_symbols, raw_book_name, title, author, index):
    """
    装饰器。改变epub保存的名称
    TODO:存在文件存在的保存问题
    :param flag: 判断是否生效的标志
    :param remove_special_symbols: 本地方法
    :param raw_book_name:
    :param title:
    :param author:
    :param index:
    :return:
    """
    def wrapper(func):
        @wraps(func)
        def changeName(*args, **kwargs):
            if End_Chapter_index == title_map[Start_Chapter_index].next.index:
                # noinspection PyStringFormat
                name = '%s %s - %s%s.epub' % (
                    *[remove_special_symbols(s) if not raw_book_name else s for s in [title, title_map[Start_Chapter_index].title, author]],
                    '' if index is None else f'({args[0]})')
            else:
                # noinspection PyStringFormat
                name = '%s %s-%s - %s%s.epub' % (
                    *[remove_special_symbols(s) if not raw_book_name else s for s in
                      [title, title_map[Start_Chapter_index].title, title_map[End_Chapter_index].pre.title, author]],
                    '' if index is None else f'({args[0]})')
            return name
        return changeName if flag else func
    return wrapper
