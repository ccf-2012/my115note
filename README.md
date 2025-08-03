# 115


## alist / openlist
* 原 alist 分支出来叫 openlist,安装  https://doc.oplist.org.cn/guide
* 添加115网盘，使用 [getcookie.py](https://gist.github.com/ChenyangGao/d26a592a0aeb13465511c885d5c7ad61) 获取 cookie
* Note: 关掉设置 -> 全局 -> 签名所有
* 测试：浏览 115 网盘内容，获取链接，确认链接可播放


## strm
* 当前有多种生成strm的程序，这里选择的是 [p115client库](https://github.com/ChenyangGao/p115client) 作者的代码，稍作改写见： [strm115.py](strm115.py) 

```sh
python strm115.py  -s /volume1/strm/olist/emby -f 4 -b "http://<your open list ip>:5244/d/volume1/mnt/alist115/" -bp "emby"  3214185321546576924
# 在 openlist 配置中，指定 /emby 作为302转发根目录，其目录id 为3214185321546576924， 并设其挂载路径为 /volume1/mnt/alist115/
# 在本机的输出位置为 /volume1/strm/olist/emby
```
>  此 strm115.py 可完成初始的strm 创建，如果需要周期运行，跳过已存在文件，清理源上已经没有的文件，需要使用 [p115client库](https://github.com/ChenyangGao/p115client) 中的 [make_strm()函数](https://p115client.readthedocs.io/en/latest/reference/tool/download.html#p115client.tool.download.make_strm)，示例程序参见 [make_strm_115.py](make_strm_115.py)。但其生成的链接包含uid,pickcode,sha1等信息，在openlist连115网盘时不需要，另外其生成的路径需要切掉openlist挂载的根目录部分，因此需要作少量修改，见[download.py](download.py)

* 使用 [make_strm_115.py](make_strm_115.py) 的命令，类同 [strm115.py](strm115.py) 
```sh
python make_strm_115.py  -s /volume1/strm/olist/emby -f 4 -b "http://<your open list ip>:5244/d/volume1/mnt/alist115/" -bp "emby"  3214185321546576924
# 在 openlist 配置中，指定 /emby 作为302转发根目录，其目录id 为3214185321546576924， 并设其挂载路径为 /volume1/mnt/alist115/
# 在本机的输出位置为 /volume1/strm/olist/emby，生成比如这样的 strm:
# 在 /volume1/strm/olist/emby/日韩剧集/kr/一起用餐吧 (2013) {tmdb-62411}/S01 位置，文件名为 Let's Eat (2013) S01E01  - 1080p.H264.AAC_CMCTV.strm，内容为：
# http://<your open list ip>:5244/d/volume1/mnt/alist115/日韩剧集/kr/一起用餐吧%20(2013)%20{tmdb-62411}/S01/Let's%20Eat%20(2013)%20S01E01%20%20-%201080p.H264.AAC_CMCTV.mkv
```
* [download.py](download.py) 需要替换 pip 安装的 p115client 库的 tool 目录下同名文件，uv 安装的环境下，在类似 `.venv/lib/python3.12/site-packages/p115client/tool` 这样的地方


## Emby播放生成的strm库
* https://github.com/sjtuross/StrmAssistant
* 安装Plugin：下载StrmAssistant.dll ；
* 放入位置：/var/lib/emby/plugins；
* 重启 Emby


## nginx + njs
* https://github.com/nginx/njs
* https://nginx.org/en/linux_packages.html
* 依上述步䯅安装支持  ngx_http_js_module 的 nginx
* 配置文件在 /etc/nginx/nginx.conf 和 /etc/nginx/conf.d/
* 缺少的 mime.types 从网上搜索下一个


## nginx + emby
* https://github.com/bpking1/embyExternalUrl
* 取其中 emby2Alist 部分的配置，加入上述 /etc/nginx 目录；
* 参考注释修改 cond.d 中 constant.js 

## torcp
* 如果原目录没有刮削，比如目录名中没有TMDb id，则可用 torcp 进行刮削硬链，生成到一新目录中，以提交 Emby

```sh
python tp.py '/volume1/strm/emby/emby/misc/NFWeb' -d '/volume1/strm/emby/ln2misc' --tmdb-api-key='your tmdb api key' --emby-bracket --tmdb-origin-name --sep-area5 
```
* 注意源文件在115上的路径在 openlist 可访问到的位置


----

## cd2
* https://www.clouddrive2.com/download.html
* 如果不上传全程可以不用 cd2
* 未来使用 [p115client库](https://github.com/ChenyangGao/p115client) 可以完成上传功能

