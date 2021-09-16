```
把 www.wenku8.net 的轻小说在线转换成epub格式。
wenku8.net 没有版权的小说则下载 TXT 文件然后转换为 epub 文件。

wk2epub [-h] [-t] [-m] [-b] [-s search_word] [-p proxy_url] [list]

    list            一个数字列表，表示 wenku8 的书的ID（从链接可以找到）。
                    中间用空格隔开。此项请放在最后。
    -t              只获取文字，忽略图片，但是图像远程链接仍然保留在文中。
                    此开关默认关闭，即默认获取图片。
    -i              显示该书信息。
    -s search_key   按照关键词搜索书籍。
    -p proxy_url    使用代理。
    -b              把生成的epub文件直接从标准输出返回。此时list长度应为1。
    -h              显示本帮助。

    Example:        wk2epub -t 2541
    About:          https://github.com/chiro2001/Wenku8ToEpub
    Version:        2021/9/16 22:43 PM
```

感谢 Contributors。