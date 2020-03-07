```
把www.wenku8.net的轻小说在线转换成epub格式。wenku8.net没有版权的小说则下载TXT文件然后转换为epub文件。

wk2epub [-h] [-t] [-m] [-b] [list]

    list            一个数字列表，中间用空格隔开

    -t              只获取文字，忽略图片。
                    但是图像远程连接仍然保留在文中。
                    此开关默认关闭，即默认获取图片。

    -m              多线程模式。
                    该开关已默认打开。

    -i              显示该书信息。

    -b              把生成的epub文件直接从stdio返回。
                    此时list长度应为1。
                    调试用。

    -h              显示本帮助。

调用示例:
    wk2epub -t 1 1213

关于:
    https://github.com/LanceLiang2018/Wenku8ToEpub

版本:
    2020/3/8 1:45 AM
```