ffmpeg -y -i cn.mp4 -i cn.wav -map '0:v' -map '1:a' -c:v  libx264 -c:a aac cnout.mp4
ffmpeg -y -i en.mp4 -i en.wav -map 0:v -map 1:a -c:v  libx264 -c:a aac enout.mp4


0.
\venv\Lib\site-packages\TTS\utils\manage.py ,大约 389 行附近，def download_model 方法中，注释掉如下代码


1. tts/utils/manage.py 532 line _download_zip_file

	def _download_zip_file:
		proxies=None
        if os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'):
            proxies = {
                "http": os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'),
                "https": os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY')
            }
        r = requests.get(file_url, stream=True,proxies=proxies)

	@staticmethod
    def _download_tar_file(file_url, output_folder, progress_bar):
        """Download the github releases"""
        # download the file
        proxies=None
        if os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'):
            proxies = {
                "http": os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'),
                "https": os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY')
            }
        r = requests.get(file_url, stream=True,proxies=proxies)


    def _download_model_files(file_urls, output_folder, progress_bar):
        """Download the github releases"""
        proxies=None
        if os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'):
            proxies = {
                "http": os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'),
                "https": os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY')
            }

2. tts/vc/modules/freevc/wavlm

	def get_wavlm():
		print(f" > Downloading WavLM model to {output_path} ...")
        if os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'):
            # 创建ProxyHandler对象
            proxy_support = urllib.request.ProxyHandler({"http": os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'),"https":os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY')})

            # 创建Opener
            opener = urllib.request.build_opener(proxy_support)

            # 安装Opener
            urllib.request.install_opener(opener)

        urllib.request.urlretrieve(model_uri, output_path)


3. E:\python\tts\venv\Lib\site-packages\fsspec\implementations\http.py

    async def _get_file(
        self, rpath, lpath, chunk_size=5 * 2**20, callback=_DEFAULT_CALLBACK, **kwargs
    ):
        print(f'%%%%%%%%%%%%%%%%%%%{rpath=},{lpath=}')
        import os
        if os.path.exists(lpath) and os.path.getsize(lpath)>16000:
            print('存在')
            return True


		proxy=os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY')
        async with session.get(self.encode_url(rpath), proxy=proxy if proxy else None,**kw) as r: